import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are a world-class software engineer. You write ONE complete source file per response.

OUTPUT CONTRACT — the single most important rule:
- Your ENTIRE response is saved verbatim as the requested file
- Output ONLY raw file contents — no markdown fences, no ===FILE=== markers, no filenames, no explanations, no greetings
- The first character of your response is the first character of the file

Read the spec_summary carefully. It tells you exactly what to build. Implement everything relevant to the requested file.

NEVER reference image files (.png, .jpg, .gif, .svg files, favicons) in HTML or CSS — you cannot create binary assets and they will 404. For visuals use emoji, Unicode symbols, inline SVG elements, or pure CSS shapes instead.

COMPLETENESS RULES:
- Every feature described in the spec that belongs in this file must be implemented and working
- No stubs, no TODOs, no placeholder comments, no empty functions
- Every interactive element must respond to user input; every button click must do something real
- Data that should persist must use localStorage (browser) or files/DB (server)
- Write enough code to make it actually work — if it needs 500 lines, write 500 lines

QUALITY RULES:
- Real variable names, not x, y, temp
- Handle edge cases — empty lists, invalid input
- Initialize properly on load — restore saved state, set up event listeners, start loops
- For HTML: write all visible content directly in the markup (never an empty shell rendered from JS), and link styles.css and app.js
- For JS: reference the actual element IDs and classes from the already-generated HTML shown in the prompt
- The file must be complete — not a fragment, the whole file"""

class CoderInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    stack_target: str
    spec_summary: str
    file_plan: list[dict]
    archetype: str = "single_page_app"
    product_type: str = "web_app"
    contract: dict = {}
    fix_feedback: str = ""
    findings: list[dict] = []


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
                "\n\nARCHETYPE: GAME — Write a COMPLETE working game, not a stub.\n"
                "For an idle clicker game you MUST include ALL of these:\n\n"
                "HTML (index.html):\n"
                "- Currency display: <div id='currency'>Coins: <span id='coin-count'>0</span></div>\n"
                "- Main click button: <button id='main-clicker'>Click!</button>\n"
                "- Characters/units section, upgrades section, stats panel\n\n"
                "JavaScript (app.js) MUST include:\n"
                "- gameState object, click handler, buy/upgrade functions,\n"
                "- game loop with setInterval, updateUI(), save/load with localStorage,\n"
                "- DOMContentLoaded listener that starts the game\n"
            )
        elif archetype in ["admin_panel", "tool"]:
            archetype_guidance = (
                f"\n\nARCHETYPE: {archetype.upper()}\n"
                "- Include complete forms with <input>, <select>, <button> elements\n"
                "- All form submissions handled via addEventListener\n"
            )

        # ── Per-file generation ────────────────────────────────────────────
        # One Ollama call per planned file. The file PATH comes from the plan
        # (never parsed from model output), and the model's entire response IS
        # the file content — no ===FILE:=== format for small models to fumble.
        for file_idx, file_entry in enumerate(file_plan):
            planned_path = self._sanitize_path(file_entry.get("path", ""))
            if not planned_path:
                logger.warning("Coder: skipping unplannable path %r", file_entry.get("path"))
                continue
            ext = planned_path.rsplit(".", 1)[-1].lower() if "." in planned_path else ""

            if all_generated:
                prior_summary = json.dumps([
                    {"path": f["relative_path"], "preview": f.get("content_preview", "")[:300]}
                    for f in all_generated
                ], indent=2)
            else:
                prior_summary = "none yet"

            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target}{stack_warning}\n"
                f"ARCHETYPE: {archetype}{archetype_guidance}\n"
                f"Requirement:\n{input_data.requirement}\n\n"
                f"Spec Summary:\n{input_data.spec_summary}\n\n"
                f"Files already generated (path + preview):\n{prior_summary}\n"
                f"{feedback_section}\n\n"
                f"Write file {file_idx + 1} of {len(file_plan)}: {planned_path}\n"
                f"Purpose: {file_entry.get('description', '')}\n\n"
                f"OUTPUT RULES — CRITICAL:\n"
                f"- Your ENTIRE response will be saved verbatim as {planned_path}\n"
                f"- Output ONLY the raw file contents\n"
                f"- NO markdown code fences, NO ===FILE=== markers, NO filenames, NO explanations\n"
                f"- Complete, working code — no stubs, TODOs, or placeholder comments"
            )

            content = ""
            last_err = ""
            for attempt in range(2):
                response = await self.provider.complete(
                    ModelRequest(
                        prompt=prompt if attempt == 0 else prompt +
                            "\n\nYOUR PREVIOUS ATTEMPT WAS EMPTY OR INVALID. Output the complete raw file contents NOW.",
                        system_prompt=load_system_prompt("coder", _CODER_SYSTEM_DEFAULT),
                        temperature=0.2 + (attempt * 0.1),
                        max_tokens=8192,
                    )
                )
                if not response.success:
                    last_err = response.error
                    continue
                content = self._clean_raw_output(response.content)
                if self._content_plausible(content, ext):
                    break
                last_err = f"implausible content for .{ext} ({len(content)} chars)"
                content = ""

            if not content:
                return CoderOutput(
                    success=False,
                    error=f"File {planned_path}: model produced no usable content after 2 attempts ({last_err})."
                )

            try:
                target = self.build_dir / "src" / planned_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except OSError as e:
                return CoderOutput(success=False, error=f"Could not write {planned_path}: {e}")
            all_generated.append({
                "path": str(target),
                "relative_path": f"src/{planned_path}",
                "size": len(content),
                "content_preview": content[:500],
            })
            logger.info("Coder: wrote %s (%d chars) [%d/%d]", planned_path, len(content), file_idx + 1, len(file_plan))

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
        if src_dir.exists() and input_data.contract.get("ui_layer", "html_css") == "html_css":
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

        # Post-process: detect empty shell HTML files and REGENERATE them.
        # Never substitute hardcoded template content — agents must stay
        # non-prescriptive. If a page has no real DOM elements, the model is
        # re-asked for that one file with explicit feedback about the failure.
        if src_dir.exists():
            for html_file in src_dir.rglob("*.html"):
                try:
                    content = html_file.read_text(encoding="utf-8")
                    cl = content.lower()
                    real_elements = len(re.findall(
                        r'<(input|button|select|textarea|table|form|ul|ol|canvas|p|h[1-6])[^/]',
                        cl
                    ))
                    classed_divs = len(re.findall(r'<div\s+class=["\'][^"\']+["\']', cl))
                    total_real = real_elements + classed_divs

                    is_empty = (
                        bool(re.search(r'<div\s+id=["\'][^"\']*["\']>\s*</div>', content, re.IGNORECASE)) or
                        bool(re.search(r'<body[^>]*>\s*(<script|<noscript)', content, re.IGNORECASE)) or
                        (bool(re.search(r'<(section|div|main)[^>]*>\s*<!--[^-]', content, re.IGNORECASE)) and total_real < 3) or
                        total_real < 2
                    )
                    if not is_empty:
                        continue

                    logger.warning("Coder: %s is an empty shell — regenerating via model", html_file.name)
                    others = json.dumps([
                        {"path": f["relative_path"], "preview": f.get("content_preview", "")[:300]}
                        for f in all_generated
                        if f.get("path") != str(html_file)
                    ], indent=2)
                    regen_prompt = (
                        f"Project: {input_data.project_name}\n"
                        f"Requirement:\n{input_data.requirement}\n\n"
                        f"Spec Summary:\n{input_data.spec_summary}\n\n"
                        f"Other generated files (path + preview):\n{others}\n\n"
                        f"Rewrite the file {html_file.name}. Your previous version was REJECTED because it "
                        f"was an empty shell: no real UI elements, placeholder comments, or content rendered "
                        f"only from JavaScript.\n\n"
                        f"REQUIREMENTS:\n"
                        f"- Write ALL UI elements directly in the HTML: headings, buttons, inputs, sections, "
                        f"cards — everything the requirement needs, visible in the markup\n"
                        f"- Link styles.css and app.js\n"
                        f"- NO placeholder comments, NO empty container divs\n\n"
                        f"OUTPUT RULES — CRITICAL:\n"
                        f"- Your ENTIRE response is saved verbatim as {html_file.name}\n"
                        f"- Output ONLY the raw HTML — no markdown fences, no explanations"
                    )
                    response = await self.provider.complete(
                        ModelRequest(
                            prompt=regen_prompt,
                            system_prompt=load_system_prompt("coder", _CODER_SYSTEM_DEFAULT),
                            temperature=0.3,
                            max_tokens=8192,
                        )
                    )
                    if not response.success:
                        logger.warning("Coder: regeneration call failed for %s: %s — leaving as-is for validator retry", html_file.name, response.error)
                        continue
                    fixed = self._clean_raw_output(response.content)
                    fixed_real = len(re.findall(
                        r'<(input|button|select|textarea|table|form|ul|ol|canvas|p|h[1-6])[^/]',
                        fixed.lower()
                    )) + len(re.findall(r'<div\s+class=["\'][^"\']+["\']', fixed.lower()))
                    if self._content_plausible(fixed, "html") and fixed_real >= 2:
                        html_file.write_text(fixed, encoding="utf-8")
                        logger.info("Coder: regenerated %s (%d chars, %d real elements)", html_file.name, len(fixed), fixed_real)
                        for f in all_generated:
                            if f.get("path") == str(html_file):
                                f["content_preview"] = fixed[:500]
                                f["size"] = len(fixed)
                    else:
                        logger.warning("Coder: regeneration for %s still weak — leaving original for validator retry", html_file.name)
                except Exception as e:
                    logger.warning("Could not regenerate empty shell %s: %s", html_file.name, e)

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

        # Post-process: inject guaranteed working tab JS
        # Scans all HTML for tab patterns and ensures app.js has real tab switching code
        if src_dir.exists():
            all_html = list(src_dir.rglob("*.html"))
            has_tabs = False
            for html_file in all_html:
                try:
                    content = html_file.read_text(encoding="utf-8").lower()
                    if any(p in content for p in ["tab-btn", "nav-tab", "tab-panel", "tab-content", 'class="tab']):
                        has_tabs = True
                        break
                except Exception:
                    pass

            if has_tabs:
                app_js = src_dir / "app.js"
                existing_js = ""
                if app_js.exists():
                    existing_js = app_js.read_text(encoding="utf-8")

                tab_js = """
// ===== Universal Tab Switcher (TESSR-LOGIC injected) =====
(function() {
  function initTabs() {
    // Pattern 1: buttons with data-tab
    document.querySelectorAll('[data-tab]').forEach(btn => {
      btn.addEventListener('click', function() {
        const target = this.dataset.tab;
        activateTab(this, target, '[data-tab]');
      });
    });
    // Pattern 2: .tab-btn class
    document.querySelectorAll('.tab-btn, .nav-tab').forEach(btn => {
      btn.addEventListener('click', function() {
        const target = this.dataset.tab || this.dataset.target || this.getAttribute('href')?.replace('#','') || this.id?.replace('-btn','');
        if (target) activateTab(this, target, '.tab-btn, .nav-tab');
      });
    });
    // Pattern 3: nav links that match section/panel IDs
    document.querySelectorAll('nav a, .navbar a').forEach(link => {
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) {
        link.addEventListener('click', function(e) {
          const target = href.replace('#','');
          const panel = document.getElementById(target);
          if (panel) {
            e.preventDefault();
            activateTab(this, target, 'nav a, .navbar a');
          }
        });
      }
    });
    // Activate first visible tab
    const firstBtn = document.querySelector('[data-tab], .tab-btn');
    if (firstBtn) firstBtn.click();
  }

  function activateTab(clickedBtn, targetId, selector) {
    // Deactivate siblings
    const parent = clickedBtn.closest('.tabs,.tab-nav,nav,.navbar') || clickedBtn.parentElement;
    parent.querySelectorAll(selector).forEach(b => {
      b.classList.remove('active');
      b.style.opacity = '0.7';
      b.style.transform = 'scale(1)';
    });
    // Activate clicked
    clickedBtn.classList.add('active');
    clickedBtn.style.opacity = '1';
    clickedBtn.style.transform = 'scale(1.05)';
    // Hide all panels
    document.querySelectorAll('.tab-panel,.tab-content,[data-panel],section[id],div[id$="-tab"],div[id$="-panel"],div[id$="-content"]').forEach(p => {
      p.style.display = 'none';
      p.classList.remove('active');
    });
    // Show target panel
    const panel = document.getElementById(targetId) ||
                  document.querySelector('[data-panel="' + targetId + '"]') ||
                  document.querySelector('#' + targetId + '-panel') ||
                  document.querySelector('#' + targetId + '-content') ||
                  document.querySelector('#' + targetId + '-tab');
    if (panel) {
      panel.style.display = 'block';
      panel.classList.add('active');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTabs);
  } else {
    initTabs();
  }
})();
// ===== End Universal Tab Switcher =====
"""
                # Always inject/replace tab JS — don't check if it exists
                if existing_js:
                    # Remove any previous injection
                    import re as _re
                    existing_js = _re.sub(
                        r'// ===== Universal Tab Switcher.*?// ===== End Universal Tab Switcher =====\n?',
                        '', existing_js, flags=_re.DOTALL
                    )
                    app_js.write_text(existing_js + "\n" + tab_js, encoding="utf-8")
                else:
                    app_js.write_text(tab_js, encoding="utf-8")
                logger.info("Coder: injected/refreshed universal tab switcher in app.js")

        return CoderOutput(success=True, generated_files=all_generated)

    _FENCE_RE = None  # set lazily

    def _clean_raw_output(self, text: str) -> str:
        """Normalize a whole-response-is-the-file output: strip markdown fences,
        stray ===FILE=== markers, and leading chatter before obvious file starts."""
        t = (text or "").strip()
        # Strip a single wrapping markdown fence
        m = re.match(r"^```[a-zA-Z0-9_-]*\n(.*?)\n?```\s*$", t, re.DOTALL)
        if m:
            t = m.group(1).strip()
        # Strip marker lines the model may still emit despite instructions
        t = re.sub(r"^\s*===FILE:[^\n]*===\s*\n", "", t)
        t = re.sub(r"^\s*(?:<!--|/\*)\s*FILE:[^\n]*(?:-->|\*/)\s*\n", "", t)
        t = re.sub(r"\n?===END===\s*$", "", t)
        # If there is chatter before the real content, cut to the first
        # recognizable file start (doctype/html tag, css rule/comment, js token)
        starts = [t.find(x) for x in ("<!DOCTYPE", "<!doctype", "<html")]
        starts = [x for x in starts if x > 0]
        if starts and t.lstrip()[0] not in "<{/":
            t = t[min(starts):]
        return t.strip()

    def _content_plausible(self, content: str, ext: str) -> bool:
        """Cheap sanity check that content looks like the right kind of file."""
        if len(content) < 40:
            return False
        c = content.lower()
        if ext == "html":
            return "<html" in c or "<!doctype" in c or "<body" in c
        if ext == "css":
            return "{" in content and "}" in content
        if ext == "js":
            return any(k in content for k in ("function", "=>", "addEventListener",
                                              "document.", "const ", "let ", "var "))
        if ext == "json":
            try:
                import json as _json
                _json.loads(content)
                return True
            except Exception:
                return False
        return True

    def _write_result(self, path: str, body: str, results: list) -> None:
        """Sanitize, write, and record one parsed file. Never raises — a bad
        path or OS error is logged and skipped so one garbage filename cannot
        kill the pipeline (previously '>' in a name crashed on Windows)."""
        rel_path = self._sanitize_path(path)
        if not rel_path or not body:
            return
        try:
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        except OSError as e:
            logger.warning("Coder: could not write %r: %s — skipping", rel_path, e)
            return
        results.append({
            "path": str(target),
            "relative_path": f"src/{rel_path}",
            "size": len(body),
            "content_preview": body[:500],
        })

    def _parse_files(self, raw: str) -> list[dict]:
        results = []

        # Normalize comment-style file markers models drift into
        # (<!-- FILE: x --> or /* FILE: x */) to the canonical format,
        # so multi-file outputs split correctly no matter the marker style.
        raw = re.sub(
            r'(?:<!--|/\*)\s*(?:===)?\s*FILE:\s*([^\n*>]+?)\s*(?:===)?\s*(?:-->|\*/)',
            r'===FILE: \1===',
            raw,
            flags=re.IGNORECASE,
        )

        # Primary: ===FILE: path=== format
        parts = re.split(r'===FILE:\s*', raw)
        for part in parts[1:]:
            header, _, body = part.partition('\n')
            path = header.replace('===', '').strip()
            body = re.split(r'===END===|===FILE:', body)[0]
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            body = body.strip('\n')
            self._write_result(path, body, results)

        if results:
            logger.info("Coder parsed %d files (===FILE: format)", len(results))
            return results

        # Fallback: comment-style markers models drift into,
        # e.g. <!-- FILE: index.html --> or /* FILE: styles.css */
        comment_pattern = re.compile(
            r'(?:<!--|/\*)\s*(?:===)?\s*FILE:\s*([^\n*>]+?)\s*(?:===)?\s*(?:-->|\*/)\s*\n'
            r'(.*?)'
            r'(?=(?:<!--|/\*)\s*(?:===)?\s*FILE:|\Z)',
            re.DOTALL | re.IGNORECASE,
        )
        for match in comment_pattern.finditer(raw):
            body = match.group(2).strip()
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            body = re.sub(r'===END===\s*$', '', body).strip('\n')
            if len(body) < 10:
                continue
            self._write_result(match.group(1), body, results)

        if results:
            logger.info("Coder parsed %d files (comment-marker fallback)", len(results))
            return results

        # Fallback: markdown code blocks with filenames
        md_pattern = re.compile(
            r'(?:(?:\*\*|__)([^*_\n]+\.\w+)(?:\*\*|__)\s*\n)?'
            r'```(?:\w+)?\n'
            r'(?://\s*([^\n]+\.\w+)\n)?'
            r'(.*?)'
            r'```',
            re.DOTALL
        )
        for match in md_pattern.finditer(raw):
            path = match.group(1) or match.group(2)
            body = (match.group(3) or "").strip()
            if not path or not body or len(body) < 10:
                continue
            self._write_result(path.strip(), body, results)

        if results:
            logger.info("Coder parsed %d files (markdown fallback)", len(results))
            return results

        # Last resort: heading-style file sections
        any_file_pattern = re.compile(
            r'(?:^|\n)#+\s*([^\n]+\.(html|css|js|py|json|txt))\s*\n(.*?)(?=\n#+\s|\Z)',
            re.DOTALL | re.MULTILINE
        )
        for match in any_file_pattern.finditer(raw):
            body = match.group(3).strip()
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            if len(body) < 20:
                continue
            self._write_result(match.group(1).strip(), body, results)

        if results:
            logger.info("Coder parsed %d files (heading fallback)", len(results))

        return results

    _ILLEGAL_FS_CHARS = '<>:"|?*'

    def _sanitize_path(self, raw: str) -> str:
        """Strip drive letters, slashes, src/ prefix, path traversal, model
        markup artifacts, and characters illegal in Windows filenames."""
        raw = (raw or "").strip()
        # Remove markup junk models wrap around filenames
        for junk in ("-->", "<!--", "*/", "/*", "```", "**", "__", "`", "'", '"'):
            raw = raw.replace(junk, "")
        raw = raw.strip().strip("=").strip()
        # Remove Windows drive letters (C:\, D:\, etc.)
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:]
        raw = raw.lstrip("/\\")
        if raw.lower().startswith("src/") or raw.lower().startswith("src\\"):
            raw = raw[4:]
            raw = raw.lstrip("/\\")
        parts = raw.replace("\\", "/").split("/")
        safe = []
        for p in parts:
            p = "".join(ch for ch in p if ch not in self._ILLEGAL_FS_CHARS and ord(ch) >= 32).strip()
            if p and p != "." and p != "..":
                safe.append(p)
        # Final component must look like a real filename (has an extension)
        if not safe or "." not in safe[-1]:
            return ""
        joined = "/".join(safe)
        try:
            test = (self.build_dir / "src" / joined).resolve()
            src_root = (self.build_dir / "src").resolve()
            test.relative_to(src_root)
        except (ValueError, OSError):
            logger.warning("Rejected unsafe path: %s", raw)
            return ""
        return joined
