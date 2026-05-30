import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are a world-class software engineer. Write complete, production-quality source code based on the spec.

OUTPUT FORMAT — only file blocks:
===FILE: filename.ext===
[complete file content]
===END===

Read the spec_summary carefully. It tells you exactly what to build. Implement everything it describes.

COMPLETENESS RULES — these apply to every project type:
- Every feature described in the spec must be implemented and working
- No stubs, no TODOs, no placeholder comments, no empty functions
- Every interactive element must respond to user input
- Every button click must do something real
- Every form must process and store data
- Data that should persist must use localStorage (browser) or files/DB (server)
- Write enough code to make the project actually work — if it needs 500 lines, write 500 lines

QUALITY RULES:
- Real variable names, not x, y, temp
- Handle edge cases — what if the list is empty, what if input is invalid
- Format numbers, dates, and output appropriately for the context
- Auto-save important state
- Initialize the app properly on load — restore saved state, set up event listeners, start loops

OUTPUT RULES:
- Link stylesheet and scripts in every HTML file
- Write all visible content in HTML — do not render content exclusively from JavaScript
- Use the ===FILE: === format for every file — no exceptions
- Every file must be complete — not a fragment, the whole file"""

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
                    "\n\nARCHETYPE: GAME — Write a COMPLETE working game, not a stub.\n"
                    "For an idle clicker game you MUST include ALL of these:\n\n"
                    "HTML (index.html):\n"
                    "- Currency display: <div id='currency'>Coins: <span id='coin-count'>0</span></div>\n"
                    "- Main click button: <button id='main-clicker'>Click!</button>\n"
                    "- Characters/units section with all 10 characters listed\n"
                    "- Each character: name, description, cost, owned count, buy button\n"
                    "- Upgrades/prestige section\n"
                    "- Stats panel\n\n"
                    "JavaScript (app.js) MUST include ALL of this:\n"
                    "- gameState object: { coins, totalCoins, coinsPerClick, coinsPerSecond, prestigeCount, prestigeMultiplier, characters: {}, upgrades: {} }\n"
                    "- ALL 10 characters as objects: { name, description, baseCost, baseCps, owned, unlocked }\n"
                    "- formatNumber(n) function: returns '1.5K', '2.3M', '1.1B' etc\n"
                    "- clickMain() function: adds coins, triggers animation\n"
                    "- buyCharacter(id) function: deducts cost, adds owned, recalculates CPS\n"
                    "- calculateCPS() function: sums all character contributions\n"
                    "- prestige() function: resets progress, adds multiplier\n"
                    "- gameLoop with setInterval(tick, 1000): adds coinsPerSecond each tick\n"
                    "- updateUI() function: updates all display elements\n"
                    "- saveGame() / loadGame() with localStorage\n"
                    "- Auto-save every 30 seconds\n"
                    "- DOMContentLoaded listener that loads save and starts game loop\n"
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
                    max_tokens=16384,
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
                    # Count meaningful content elements
                    real_elements = len(re.findall(
                        r'<(input|button|select|textarea|table|form|ul|ol|canvas|p|h[1-6])[^/]',
                        cl
                    ))
                    # Count divs/spans with real class names (not just containers)
                    classed_divs = len(re.findall(r'<div\s+class=["\'][^"\']+["\']', cl))
                    total_real = real_elements + classed_divs

                    is_empty = (
                        # Empty app shell with nothing inside
                        bool(re.search(r'<div\s+id=["\'][^"\']*["\']>\s*</div>', content, re.IGNORECASE)) or
                        # Body contains only script tags
                        bool(re.search(r'<body[^>]*>\s*(<script|<noscript)', content, re.IGNORECASE)) or
                        # Has comments as placeholders AND almost no real content
                        (bool(re.search(r'<(section|div|main)[^>]*>\s*<!--[^-]', content, re.IGNORECASE)) and total_real < 3) or
                        # Truly nothing there
                        total_real < 2
                    )
                    if not is_empty:
                        continue

                    # Build requirement-aware repair page
                    page_name = html_file.stem.replace("-", " ").replace("_", " ").title()
                    req_lower = (input_data.requirement or "").lower()

                    # Detect if this is a tab-based app
                    is_tab_app = any(w in req_lower for w in ["tab", "color tab", "coloured"])
                    # Detect colors for tabs
                    tab_colors = []
                    color_map = {"red":"#e74c3c","green":"#27ae60","blue":"#2980b9","yellow":"#f39c12","purple":"#8e44ad","orange":"#e67e22","pink":"#e91e8c"}
                    for color, hex_val in color_map.items():
                        if color in req_lower:
                            tab_colors.append((color.title(), hex_val))

                    if is_tab_app and tab_colors:
                        tabs_html = "\n".join([
                            f'  <button class="tab-btn" data-tab="tab-{c[0].lower()}" style="background:{c[1]};color:white;padding:12px 24px;border:none;border-radius:8px;font-size:1rem;font-weight:bold;cursor:pointer;margin:4px;">{c[0]}</button>'
                            for c in tab_colors
                        ])
                        panels_html = "\n".join([f'''  <div class="tab-panel" id="tab-{c[0].lower()}" style="display:none;padding:1rem;">
    <h2 style="color:{c[1]}">{c[0]} Events</h2>
    <div style="display:flex;gap:8px;margin:1rem 0;">
      <input type="text" id="title-{c[0].lower()}" placeholder="Event title..." style="flex:1;padding:8px;border-radius:6px;border:1px solid #ccc;">
      <input type="date" id="date-{c[0].lower()}" style="padding:8px;border-radius:6px;border:1px solid #ccc;">
      <button onclick="addEvent('{c[0].lower()}')" style="background:{c[1]};color:white;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:bold;">+ Add</button>
    </div>
    <div id="events-{c[0].lower()}"></div>
  </div>''' for c in tab_colors])

                        repaired = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{input_data.project_name}</title>
  <link rel="stylesheet" href="styles.css">
  <style>
    .tab-btn.active {{ transform: scale(1.05); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
    .tab-panel {{ animation: fadeIn 0.2s ease; }}
    .event-item {{ display:flex;justify-content:space-between;align-items:center;padding:10px;margin:6px 0;background:rgba(255,255,255,0.1);border-radius:6px;border-left:4px solid currentColor; }}
    .delete-btn {{ background:#e74c3c;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer; }}
    @keyframes fadeIn {{ from{{opacity:0;transform:translateY(-4px)}} to{{opacity:1;transform:translateY(0)}} }}
  </style>
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">{input_data.project_name}</div>
  </nav>
  <main class="container" style="padding:2rem;">
    <h1>{page_name}</h1>
    <div style="display:flex;gap:8px;margin:1.5rem 0;flex-wrap:wrap;">
{tabs_html}
    </div>
{panels_html}
  </main>
  <script>
    const COLORS = {{{",".join([f'"{c[0].lower()}":\"{c[1]}\"' for c in tab_colors])}}};
    
    function loadEvents(tab) {{
      return JSON.parse(localStorage.getItem('events_' + tab) || '[]');
    }}
    function saveEvents(tab, events) {{
      localStorage.setItem('events_' + tab, JSON.stringify(events));
    }}
    function renderEvents(tab) {{
      const events = loadEvents(tab);
      const container = document.getElementById('events-' + tab);
      if (!container) return;
      if (events.length === 0) {{
        container.innerHTML = '<p style="color:#888;text-align:center;padding:1rem;">No events yet. Add one above!</p>';
        return;
      }}
      container.innerHTML = events.map((e, i) => `
        <div class="event-item" style="color:${{COLORS[tab]}}">
          <div><strong>${{e.title}}</strong>${{e.date ? ' — ' + e.date : ''}}</div>
          <button class="delete-btn" onclick="deleteEvent('${{tab}}',${{i}})">Delete</button>
        </div>
      `).join('');
    }}
    function addEvent(tab) {{
      const title = document.getElementById('title-' + tab).value.trim();
      const date = document.getElementById('date-' + tab).value;
      if (!title) {{ alert('Please enter an event title'); return; }}
      const events = loadEvents(tab);
      events.push({{title, date, created: new Date().toISOString()}});
      saveEvents(tab, events);
      document.getElementById('title-' + tab).value = '';
      document.getElementById('date-' + tab).value = '';
      renderEvents(tab);
    }}
    function deleteEvent(tab, index) {{
      const events = loadEvents(tab);
      events.splice(index, 1);
      saveEvents(tab, events);
      renderEvents(tab);
    }}
    function switchTab(tabId) {{
      document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      const panel = document.getElementById(tabId);
      if (panel) panel.style.display = 'block';
      const btn = document.querySelector(`[data-tab="${{tabId}}"]`);
      if (btn) btn.classList.add('active');
      renderEvents(tabId.replace('tab-', ''));
    }}
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    }});
    // Activate first tab
    const firstTab = document.querySelector('.tab-btn');
    if (firstTab) firstTab.click();
    // Enter key to add
    document.querySelectorAll('input[id^="title-"]').forEach(input => {{
      input.addEventListener('keydown', e => {{
        if (e.key === 'Enter') {{
          const tab = input.id.replace('title-', '');
          addEvent(tab);
        }}
      }});
    }});
  </script>
</body>
</html>"""
                    else:
                        # Generic functional repair template
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
    </div>
    <div class="card">
      <div class="flex-between" style="margin-bottom:1rem;">
        <h2>Items</h2>
        <button class="btn" id="add-btn">+ Add New</button>
      </div>
      <div id="add-form" style="display:none;margin-bottom:1rem;padding:1rem;border:1px solid var(--border);border-radius:8px;">
        <input type="text" id="item-title" placeholder="Enter title..." style="margin-bottom:8px;">
        <div class="flex" style="gap:8px;margin-top:8px;">
          <button class="btn" id="save-btn">Save</button>
          <button class="btn btn-secondary" id="cancel-btn">Cancel</button>
        </div>
      </div>
      <div id="items-list"><p style="color:var(--muted);text-align:center;padding:2rem;">No items yet.</p></div>
    </div>
  </main>
  <script>
    const KEY = 'items_{html_file.stem}';
    let items = JSON.parse(localStorage.getItem(KEY) || '[]');
    function render() {{
      const el = document.getElementById('items-list');
      if (!items.length) {{ el.innerHTML = '<p style="color:var(--muted);text-align:center;padding:2rem;">No items yet.</p>'; return; }}
      el.innerHTML = items.map((item, i) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;margin:4px 0;background:var(--surface);border-radius:6px;"><span>${{item.title}}</span><button onclick="del(${{i}})" style="background:#e74c3c;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;">Delete</button></div>`).join('');
    }}
    function del(i) {{ items.splice(i,1); localStorage.setItem(KEY,JSON.stringify(items)); render(); }}
    document.getElementById('add-btn').onclick = () => document.getElementById('add-form').style.display = 'block';
    document.getElementById('cancel-btn').onclick = () => document.getElementById('add-form').style.display = 'none';
    document.getElementById('save-btn').onclick = () => {{
      const t = document.getElementById('item-title').value.trim();
      if (!t) return;
      items.push({{title:t,created:new Date().toISOString()}});
      localStorage.setItem(KEY,JSON.stringify(items));
      document.getElementById('item-title').value = '';
      document.getElementById('add-form').style.display = 'none';
      render();
    }};
    render();
  </script>
</body>
</html>"""

                    html_file.write_text(repaired, encoding="utf-8")
                    logger.info("Coder: repaired empty shell %s with functional template", html_file.name)
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

    def _parse_files(self, raw: str) -> list[dict]:
        results = []

        # Primary: ===FILE: path=== format
        parts = re.split(r'===FILE:\s*', raw)
        for part in parts[1:]:
            header, _, body = part.partition('\n')
            path = header.replace('===', '').strip()
            body = re.split(r'===END===|===FILE:', body)[0]
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
            logger.info("Coder parsed %d files (===FILE: format)", len(results))
            return results

        # Fallback: markdown code blocks with filenames
        # Matches: ```lang\n// filename.ext\ncode``` or **filename.ext**\n```\ncode```
        md_pattern = re.compile(
            r'(?:(?:\*\*|__)([^*_\n]+\.\w+)(?:\*\*|__)\s*\n)?'  # optional **filename**
            r'```(?:\w+)?\n'                                        # ```lang
            r'(?://\s*([^\n]+\.\w+)\n)?'                           # optional // filename
            r'(.*?)'                                                 # code content
            r'```',
            re.DOTALL
        )
        for match in md_pattern.finditer(raw):
            bold_name = match.group(1)
            comment_name = match.group(2)
            body = match.group(3).strip()
            path = bold_name or comment_name
            if not path or not body or len(body) < 10:
                continue
            rel_path = self._sanitize_path(path.strip())
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
            logger.info("Coder parsed %d files (markdown fallback)", len(results))
            return results

        # Last resort: try to find any HTML/JS/CSS content blocks with file headers
        any_file_pattern = re.compile(
            r'(?:^|\n)#+\s*([^\n]+\.(html|css|js|py|json|txt))\s*\n(.*?)(?=\n#+\s|\Z)',
            re.DOTALL | re.MULTILINE
        )
        for match in any_file_pattern.finditer(raw):
            path = match.group(1).strip()
            body = match.group(3).strip()
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            if len(body) < 20:
                continue
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
            logger.info("Coder parsed %d files (heading fallback)", len(results))

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
