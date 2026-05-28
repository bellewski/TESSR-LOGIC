import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are a world-class full-stack software engineer.

OUTPUT FORMAT ONLY -- no explanations, no markdown prose:
===FILE: filename===
code here
===END===

CRITICAL HTML REQUIREMENTS:
- EVERY HTML file MUST have <link rel="stylesheet" href="styles.css"> in <head>
- EVERY HTML file MUST have <script src="app.js" defer></script> before </body>
- Navigation MUST use: <nav class="navbar"> with <a class="nav-link"> links
- Page sections MUST use: <main class="container"> or <div class="container">
- Cards MUST use: <div class="card">
- Buttons MUST use: <button class="btn">
- Multi-page: ALL pages link same styles.css and app.js, nav links use href="page.html"
- NEVER use href="#" for navigation between pages
- ALL content must be in the HTML directly -- never rely on JS to render initial content
- NEVER use <!-- comments --> as placeholders for DOM elements
- NEVER write empty sections like <div id="app"></div> or <section><!-- content --></section>
- Every section MUST contain real <div>, <button>, <input>, <select>, <table>, <p> elements
- Every element that JS needs MUST have an id="" or class="" already in the HTML
- Write ALL the HTML up front -- do NOT defer content to JavaScript rendering

CRITICAL JS REQUIREMENTS:
- ALL buttons must have real addEventListener handlers
- localStorage for all data persistence
- NEVER leave empty functions or TODO comments
- If using sections/tabs: show/hide with CSS classes, not innerHTML replacement

CRITICAL CSS CLASS CONTRACT (Coder and UI Designer share these):
- Navigation wrapper: class="navbar"
- Nav links: class="nav-link"
- Page wrapper: class="container"
- Cards/panels: class="card"
- Buttons: class="btn" or class="btn btn-primary"
- Form inputs: standard input/select/textarea elements
- Active nav: class="active" on current page link
- Stats/metric boxes: class="stat-card"
- Tables: class="table"

QUALITY BAR:
- Complete, working, production-ready code only
- No stubs, no TODOs, no placeholders
- Every feature in the requirement must actually work
- Real data, real interactions, real persistence"""

class CoderInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    stack_target: str
    spec_summary: str
    file_plan: list[dict]
    archetype: str = "single_page_app"  # from Architect — drives HTML structure decisions
    fix_feedback: str = ""
    findings: list[dict] = []  # Security findings from Hardener for fixing on retry


class CoderOutput(BaseModel):
    success: bool
    error: str = ""
    generated_files: list[dict] = []


class CoderAgent(BaseAgent[CoderInput, CoderOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: CoderInput) -> CoderOutput:
        import json
        from pathlib import Path

        all_generated: list[dict] = []
        file_plan = input_data.file_plan or []
        if not file_plan:
            return CoderOutput(success=False, error="No file_plan provided.")

        # Generate all files including CSS - ensure complete application
        # Don't filter CSS files - Coder must generate complete apps

        feedback_section = ""
        if input_data.fix_feedback:
            # Detect empty shell failure — use extra forceful prompt
            is_empty_shell_failure = (
                "empty shell" in input_data.fix_feedback.lower() or
                "placeholder comment" in input_data.fix_feedback.lower() or
                "div id='app'" in input_data.fix_feedback.lower() or
                "comment-only" in input_data.fix_feedback.lower()
            )
            if is_empty_shell_failure:
                feedback_section = (
                    f"\n\n{'='*60}\n"
                    f"CRITICAL FAILURE — YOU GENERATED EMPTY HTML SHELLS\n"
                    f"{'='*60}\n"
                    f"{input_data.fix_feedback}\n\n"
                    f"THIS IS YOUR MOST IMPORTANT RULE THIS ROUND:\n"
                    f"NEVER write <div id='app'></div> and render from JS.\n"
                    f"NEVER write <!-- section content here --> comments.\n"
                    f"EVERY HTML file MUST have real elements written directly:\n"
                    f"  <nav class='navbar'><a href='index.html'>Home</a>...</nav>\n"
                    f"  <main class='container'>\n"
                    f"    <div class='card'><h2>Title</h2><p>Content</p></div>\n"
                    f"    <button class='btn'>Click me</button>\n"
                    f"    <input type='text' placeholder='Enter value'>\n"
                    f"  </main>\n"
                    f"Write COMPLETE HTML with ALL content visible without JavaScript.\n"
                    f"{'='*60}"
                )
            else:
                feedback_section = f"\n\nFIX FEEDBACK FROM VALIDATOR:\n{input_data.fix_feedback}\nPlease address these issues in the regenerated code."
        
        findings_section = ""
        if input_data.findings:
            findings_text = "\n".join([
                f"- {f.get('severity', 'unknown')}: {f.get('description', '')} (line {f.get('line_number', 'unknown')})"
                for f in input_data.findings[:10]
            ])
            feedback_section += f"\n\nSECURITY FINDINGS TO FIX:\n{findings_text}\nYou MUST fix these security issues in your new code."

        # Adaptive batching: complex files (HTML, JS) get their own batch; simple files group together
        def _batch_size_for(f: dict) -> int:
            ext = (f.get("path", "") or "").rsplit(".", 1)[-1].lower()
            if ext in ("html", "jsx", "tsx"):
                return 1   # HTML gets solo — most context-heavy
            if ext in ("js", "ts", "py"):
                return 1   # Logic files solo — need full token budget
            return 3       # Config, CSS, JSON, MD can batch together

        batches: list[list[dict]] = []
        current_batch: list[dict] = []
        current_limit = 1

        for file_entry in file_plan:
            limit = _batch_size_for(file_entry)
            if not current_batch:
                current_batch = [file_entry]
                current_limit = limit
            elif limit == current_limit and len(current_batch) < current_limit:
                current_batch.append(file_entry)
            else:
                batches.append(current_batch)
                current_batch = [file_entry]
                current_limit = limit
        if current_batch:
            batches.append(current_batch)

        for batch_idx, batch in enumerate(batches):
            batch_json = json.dumps(batch, indent=2)
            # Give later batches a richer view of what was already generated (path + preview)
            if all_generated:
                prior_summary = json.dumps([
                    {"path": f["relative_path"], "preview": f.get("content_preview", "")[:300]}
                    for f in all_generated
                ], indent=2)
            else:
                prior_summary = "none yet"

            stack_warning = ""
            if input_data.stack_target.lower() in ["html5", "vanilla", "plain"]:
                stack_warning = "\n\n!!! CRITICAL: STACK IS HTML5/VANILLA - NO FRAMEWORKS ALLOWED !!!\nNEVER use React, JSX, Vue, Angular, imports, or any build tools.\nONLY plain HTML, CSS, and vanilla JavaScript with DOM APIs.\n"

            # Archetype-specific HTML structure guidance
            archetype = input_data.archetype or "single_page_app"
            archetype_guidance = ""
            if archetype == "multi_page_site":
                archetype_guidance = (
                    "\n\nARCHETYPE: MULTI-PAGE SITE\n"
                    "- Generate SEPARATE HTML files for each page (dashboard.html, tasks.html, etc.)\n"
                    "- Every HTML file MUST have <nav class='navbar'> with links to ALL other pages\n"
                    "- Navigation links: <a href='dashboard.html'>, <a href='tasks.html'> etc.\n"
                    "- Each page MUST have its own complete <body> content — NOT empty shells\n"
                    "- ALL pages share ONE styles.css and ONE app.js\n"
                )
            elif archetype == "dashboard":
                archetype_guidance = (
                    "\n\nARCHETYPE: DASHBOARD (single page)\n"
                    "- ONE index.html with ALL sections visible (no separate HTML files)\n"
                    "- Use <section> or <div> to separate dashboard panels\n"
                    "- Include stat cards, charts, data tables in the HTML directly\n"
                )
            elif archetype == "game":
                archetype_guidance = (
                    "\n\nARCHETYPE: GAME\n"
                    "- ONE index.html with <canvas id='gameCanvas'> element\n"
                    "- Include score display, controls, and game UI in HTML\n"
                    "- Game loop and all logic in app.js\n"
                )
            elif archetype in ["admin_panel", "tool"]:
                archetype_guidance = (
                    f"\n\nARCHETYPE: {archetype.upper()}\n"
                    "- Include complete forms with <input>, <select>, <button> elements\n"
                    "- All form submissions handled via addEventListener\n"
                )

            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target}{stack_warning}\n"
                f"ARCHETYPE: {archetype}{archetype_guidance}\n"
                f"Requirement:\n{input_data.requirement}\n\n"
                f"Spec Summary:\n{input_data.spec_summary}\n\n"
                f"Files already generated (path + preview):\n{prior_summary}\n\n"
                f"Generate ONLY these {len(batch)} files now (batch {batch_idx + 1}/{len(batches)}):\n{batch_json}"
                f"{feedback_section}\n\n"
                "Generate ONLY the listed files. "
                "ONLY output ===FILE: path.ext=== blocks followed by ===END===. "
                "NO introductions. NO explanations. NO questions. ONLY file blocks. "
                "Every file MUST contain real, working code — not stubs or TODOs."
            )

            response = await self.provider.complete(
                ModelRequest(
                    prompt=prompt,
                    system_prompt=load_system_prompt("coder", _CODER_SYSTEM_DEFAULT),
                    temperature=0.2,
                    max_tokens=8192,
                )
            )
            if not response.success:
                return CoderOutput(success=False, error=response.error)

            generated = self._parse_files(response.content)
            if not generated:
                return CoderOutput(
                    success=False,
                    error=f"Batch {batch_idx + 1}: No parseable files found. Ensure every file is wrapped in ===FILE: path.ext=== ... ===END=== format."
                )
            all_generated.extend(generated)

        if not all_generated:
            return CoderOutput(
                success=False,
                error="No parseable files found in any batch."
            )

        # Self-validation 1: reject if too many empty or stub files
        empty_count = sum(1 for f in all_generated if f.get("size", 0) < 50)
        if empty_count > len(all_generated) // 3:
            logger.warning("Coder produced %d/%d empty/stub files — treating as failure", empty_count, len(all_generated))
            return CoderOutput(success=False, error=f"Generated {empty_count}/{len(all_generated)} empty or stub files. Must write complete code for every file.")

        # Self-validation 2: warn if file_plan coverage is incomplete
        planned_paths = {self._sanitize_path(f.get("path", "")) for f in input_data.file_plan if f.get("path")}
        generated_paths = {self._sanitize_path(f.get("relative_path", "").replace("src/", "")) for f in all_generated}
        # Only check planned paths that look like source files (not docs)
        source_plan = {p for p in planned_paths if p and not p.endswith((".md", ".txt", ".rst"))}
        if source_plan:
            missing = source_plan - generated_paths
            if missing:
                logger.warning("Coder missing %d planned files: %s", len(missing), missing)
                # Don't fail — 13B model can't generate all files in one shot.
                # Smoke tester will catch missing files and trigger build-round retry.

        # Self-validation 3+4: CSS/JS quality checks removed — smoke tester handles quality validation
        # Coder's job is to generate files; let smoke tester decide if they're good enough

        # Post-process: ensure every HTML file links styles.css
        src_dir = self.build_dir / "src"
        if src_dir.exists():
            for html_file in src_dir.rglob("*.html"):
                try:
                    content = html_file.read_text(encoding="utf-8")
                    if "styles.css" not in content and "<link" not in content.lower():
                        inject = '<link rel="stylesheet" href="styles.css">'
                        if "</head>" in content:
                            content = content.replace("</head>", f"  {inject}\n</head>")
                        elif "<head>" in content:
                            content = content.replace("<head>", f"<head>\n  {inject}")
                        html_file.write_text(content, encoding="utf-8")
                        logger.info("Coder: injected styles.css link into %s", html_file.name)
                        for f in all_generated:
                            if f.get("path") == str(html_file):
                                f["content_preview"] = content[:500]
                                f["size"] = len(content)
                except Exception as e:
                    logger.warning("Could not inject stylesheet into %s: %s", html_file.name, e)

        # Post-process: repair empty shell HTML files
        # If a file has no real DOM elements, replace it with a real content template
        if src_dir.exists():
            all_html = list(src_dir.rglob("*.html"))
            nav_links = "\n".join(
                f'      <a class="nav-link" href="{h.name}">{h.stem.replace("-", " ").title()}</a>'
                for h in all_html
            )
            for html_file in all_html:
                try:
                    content = html_file.read_text(encoding="utf-8")
                    cl = content.lower()
                    real_elements = len(re.findall(
                        r'<(input|button|select|textarea|table|form|ul|ol|canvas|p|h[1-6]|div class|span)[^/]',
                        cl
                    ))
                    is_empty = (
                        re.search(r'<div\s+id=["\']app["\']>\s*</div>', content, re.IGNORECASE) or
                        re.search(r'<body[^>]*>\s*<script', content, re.IGNORECASE) or
                        real_elements < 3
                    )
                    if not is_empty:
                        continue

                    # Build a real content page from the file plan
                    page_name = html_file.stem.replace("-", " ").replace("_", " ").title()
                    # Find this file's description from file_plan
                    description = ""
                    for fp in (input_data.file_plan or []):
                        if Path(fp.get("path", "")).name == html_file.name:
                            description = fp.get("description", "")
                            break

                    repaired = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_name} — {input_data.project_name}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">{input_data.project_name}</div>
{nav_links}
  </nav>
  <main class="container">
    <div class="section-header">
      <h1>{page_name}</h1>
      <p>{description or f"Manage your {page_name.lower()} here."}</p>
    </div>
    <div class="grid grid-3" id="{html_file.stem}-stats">
      <div class="card stat-card">
        <h3>Total Items</h3>
        <p class="stat-value" id="total-count">0</p>
      </div>
      <div class="card stat-card">
        <h3>Active</h3>
        <p class="stat-value" id="active-count">0</p>
      </div>
      <div class="card stat-card">
        <h3>Completed</h3>
        <p class="stat-value" id="done-count">0</p>
      </div>
    </div>
    <div class="card" style="margin-top:1rem;">
      <div class="flex-between" style="margin-bottom:1rem;">
        <h2>{page_name}</h2>
        <button class="btn" id="add-btn">+ Add New</button>
      </div>
      <div class="flex" style="margin-bottom:1rem;gap:.5rem;">
        <input type="text" id="search-input" placeholder="Search..." style="flex:1;">
        <select id="filter-select">
          <option value="all">All</option>
          <option value="active">Active</option>
          <option value="done">Done</option>
        </select>
      </div>
      <div id="items-list">
        <p style="color:var(--muted);text-align:center;padding:2rem;">No items yet. Click "+ Add New" to get started.</p>
      </div>
    </div>
    <div class="card" id="add-form" style="margin-top:1rem;display:none;">
      <h3>Add New Item</h3>
      <div style="display:flex;flex-direction:column;gap:.75rem;margin-top:1rem;">
        <div>
          <label for="item-title">Title</label>
          <input type="text" id="item-title" placeholder="Enter title...">
        </div>
        <div>
          <label for="item-notes">Notes</label>
          <textarea id="item-notes" placeholder="Add notes..." rows="3"></textarea>
        </div>
        <div>
          <label for="item-priority">Priority</label>
          <select id="item-priority">
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <div class="flex" style="gap:.5rem;">
          <button class="btn" id="save-btn">Save</button>
          <button class="btn btn-secondary" id="cancel-btn">Cancel</button>
        </div>
      </div>
    </div>
  </main>
  <script src="app.js" defer></script>
</body>
</html>"""
                    html_file.write_text(repaired, encoding="utf-8")
                    logger.info("Coder: repaired empty shell %s with real content template", html_file.name)
                    for f in all_generated:
                        if f.get("path") == str(html_file):
                            f["content_preview"] = repaired[:500]
                            f["size"] = len(repaired)
                except Exception as e:
                    logger.warning("Could not repair empty shell %s: %s", html_file.name, e)

        # Post-process: repair missing nav links
        # Ensure every HTML file's navbar links to ALL other HTML files
        if src_dir.exists():
            all_html = list(src_dir.rglob("*.html"))
            if len(all_html) > 1:
                for html_file in all_html:
                    try:
                        content = html_file.read_text(encoding="utf-8")
                        # Find existing nav block
                        nav_match = re.search(r'<nav[^>]*class=["\'][^"\']*navbar[^"\']*["\'][^>]*>.*?</nav>', content, re.DOTALL | re.IGNORECASE)
                        if not nav_match:
                            nav_match = re.search(r'<nav[^>]*>.*?</nav>', content, re.DOTALL | re.IGNORECASE)
                        if not nav_match:
                            continue
                        nav_block = nav_match.group(0)
                        # Check which pages are missing from nav
                        missing = [h for h in all_html if h.name not in nav_block]
                        if not missing:
                            continue
                        # Inject missing links before </nav>
                        new_links = "".join(
                            f'\n    <a class="nav-link" href="{h.name}">{h.stem.replace("-", " ").replace("_", " ").title()}</a>'
                            for h in missing
                        )
                        new_nav = nav_block.replace("</nav>", f"{new_links}\n  </nav>")
                        content = content.replace(nav_block, new_nav)
                        html_file.write_text(content, encoding="utf-8")
                        logger.info("Coder: added missing nav links %s to %s", [h.name for h in missing], html_file.name)
                        for f in all_generated:
                            if f.get("path") == str(html_file):
                                f["content_preview"] = content[:500]
                                f["size"] = len(content)
                    except Exception as e:
                        logger.warning("Could not repair nav links in %s: %s", html_file.name, e)

        return CoderOutput(success=True, generated_files=all_generated)

    def _parse_files(self, raw: str) -> list[dict]:
        results = []
        # Split by ===FILE: markers (works even without ===END===)
        parts = re.split(r'===FILE:\s*', raw)
        for part in parts[1:]:
            header, _, body = part.partition('\n')
            path = header.replace('===', '').strip()
            # Strip trailing end markers or next file header
            body = re.split(r'===END===|===FILE:', body)[0]
            # Strip markdown code-block wrappers (```lang ... ```)
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            body = body.strip('\n')
            rel_path = self._sanitize_path(path)
            if not rel_path:
                continue
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": f"src/{rel_path}",
                "size": len(body),
                "content_preview": body[:500],
            })

        if results:
            logger.info("Coder parsed %d files from %d characters", len(results), len(raw))
        return results

    def _sanitize_path(self, raw: str) -> str:
        """Strip drive letters, leading slashes, src/ prefix, and path-traversal attempts."""
        import os
        # Remove Windows drive letters (C:\, D:\, etc.)
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:]
        # Remove leading slashes and backslashes
        raw = raw.lstrip("/\\")
        # Strip leading src/ since we already store under src/
        if raw.lower().startswith("src/") or raw.lower().startswith("src\\"):
            raw = raw[4:]
            raw = raw.lstrip("/\\")
        # Normalize to forward slashes, then reject any '..' components
        parts = raw.replace("\\", "/").split("/")
        safe = [p for p in parts if p and p != "." and p != ".."]
        if not safe:
            return ""
        joined = "/".join(safe)
        # Ensure it doesn't resolve outside the src directory
        test = (self.build_dir / "src" / joined).resolve()
        src_root = (self.build_dir / "src").resolve()
        try:
            test.relative_to(src_root)
        except ValueError:
            logger.warning("Path escapes src directory: %s", raw)
            return ""
        return joined
