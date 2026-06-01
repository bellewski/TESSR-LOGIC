import logging
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)


_UI_DESIGNER_SYSTEM_DEFAULT = """You are a world-class UI/UX designer. Write a complete styles.css based on the spec.

OWNERSHIP: You are the SOLE author of the visual design. The Coder wrote semantic HTML (with a
centered .container wrapper, grouped card/grid wrappers, and inline <svg> icons) but deliberately
left styling to YOU. Produce the COMPLETE, professional stylesheet — do not assume any prior CSS
exists; your stylesheet defines the entire look. Style the Coder's structural hooks: give
.container its max-width + centering + padding, lay out the card/grid wrappers as a responsive
grid of elevated cards, and size/color the inline SVG icons. If the HTML still contains emoji where
icons belong, style around it but the design must not depend on emoji.

Read the spec_summary carefully — it describes the visual design intent. Implement it precisely.

Design intelligence:
- Game → dark background, vivid accent colors, large clickable elements, clear HUD-style number displays, glowing effects
- Dashboard → clean layout, data-dense, subtle colors, readable tables and charts
- Creative/colorful → vibrant palette, bold typography
- Professional → clean whites/blues/grays, conservative layout
- Dark theme → dark backgrounds, light text, glowing accents
- Colors specified → use those exact colors as the primary palette
- If nothing specified → clean modern dark theme

Your CSS must:
- Use :root CSS variables for all colors and spacing
- Style every element the HTML uses — nothing unstyled
- Include hover, active, focus states for all interactive elements
- Be fully responsive with media queries
- Have minimum 60 rules covering all UI components

SVG SIZING (CRITICAL — the #1 cause of a giant graphic swallowing the whole page):
- An inline <svg> that has a viewBox but NO width/height and NO CSS size expands to fill its
  container and (with no fill) renders as a huge solid-black blob. You MUST prevent this.
- ALWAYS include a base rule: `svg { max-width: 100%; height: auto; display: block; }`
- Give ICON svgs explicit small dimensions by their class, e.g.
  `.logo-icon, .bento-icon, .theme-icon, .feature-icon, .step-icon { width: 24px; height: 24px; }`
  (icons should be ~16-28px, never full width).
- CONSTRAIN illustration/hero svgs: e.g. `.hero-svg, .hero-illustration svg, .feature-illustration svg
  { width: 100%; height: auto; max-height: 360px; }` so they never exceed their section.
- Give every svg an explicit fill/stroke from your palette (e.g. `svg { fill: var(--accent); }` and
  override per-context) — never leave them defaulting to black.
- Match the actual class names present in the HTML (e.g. .nav-links, .navbar, .logo-icon, .hero-svg,
  .bento-icon). If the HTML's nav list has no class, also style `nav ul { list-style: none; }` and
  `nav ul, .nav-links { display: flex; gap: 1.5rem; }` so the navbar is never a bulleted list.

MODERN DESIGN SYSTEM — hit this quality bar (this is what separates "looks like 1998"
from "looks professional"). Apply ALL of it:
- Typography: a system font stack (system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
  a clear type scale (e.g. 2.5rem h1, 1.5rem h2, 1rem body); line-height ~1.6; never tiny text.
- Spacing: a consistent scale via variables (4/8/16/24/32/48px). Generous padding; nothing cramped.
- Color: a cohesive palette — one primary, one accent, neutral grays; ensure strong text contrast.
  Use a real gradient on the header/hero (linear-gradient with 2 harmonious colors). Do NOT use
  background-size tricks like "100% 300px" on gradients — they cause ugly banding; let gradients fill.
- VISUAL DEPTH (critical — this is the #1 thing that makes a page look unfinished): the page
  body and its content sections must NOT be the same flat color. Give the body a soft tinted
  background, and put content on ELEVATED surfaces — cards/sections with their own (usually white
  or lighter) background, rounded corners, and a soft box-shadow. Every major section should sit
  in a visually distinct container, not bare text on the page background. Alternate section
  backgrounds subtly if there are many. The middle of the page must never look empty/unstyled.
- Surfaces: cards/sections with border-radius 8-16px, soft layered box-shadow
  (e.g. 0 4px 12px rgba(0,0,0,.08)), subtle borders. White/elevated cards on a tinted background.
- Layout: center content in a max-width container (~1100px) with auto margins; use CSS grid or
  flex for card lists (responsive auto-fit grid). Sticky, well-spaced navbar with clear active state.
- Motion: smooth transitions (transition: all .2s ease) on hover for buttons/cards/links;
  buttons lift or change shade on hover; cursor:pointer on all clickables.
- Buttons: padded (e.g. .6rem 1.2rem), rounded, filled-primary + outline-secondary variants,
  no default browser look.
- Forms: styled inputs with padding, border, border-radius, focus ring.
- Dark mode: if a theme toggle exists, provide a complete [data-theme="dark"] / .dark-theme
  variable override set.

MODERN 2026 RICHNESS — go beyond "clean" to "premium" (this is what separates a basic
template from a current SaaS site like Linear/Vercel/Stripe). Add these with CSS only
(no external assets — inline SVG + CSS only, fully offline):
- DISPLAY TYPOGRAPHY: oversized, bold hero heading using clamp() for fluid sizing
  (e.g. font-size: clamp(2.5rem, 6vw, 4.5rem); font-weight: 800; letter-spacing: -.02em).
- DEPTH & GLASS: glassmorphism on key cards/navbar where it fits — semi-transparent
  background + backdrop-filter: blur(12px) + a 1px translucent border + layered shadow.
- RICH BACKGROUNDS: an animated or multi-stop gradient (or subtle radial "mesh") on the
  hero, not a flat fill; optional faint grid/dot pattern via CSS gradients.
- MOTION (CSS-only, no JS needed): @keyframes fade/slide-up entrance on hero/sections;
  where supported use scroll-driven `animation-timeline: view()` for reveal-on-scroll with
  a graceful static fallback; smooth hover lifts (translateY) + shadow growth on cards.
- LAYOUT VARIETY: don't stack identical centered blocks — use a responsive bento/auto-fit
  GRID for features, alternate section backgrounds, and asymmetry where appropriate.
- MICRO-INTERACTIONS: buttons with gradient fills + hover glow; links with animated
  underlines; cards that lift and brighten on hover.
- Respect prefers-reduced-motion (disable animations) for accessibility.
Make it genuinely attractive — a designer should not be embarrassed by it.

OUTPUT FORMAT — nothing else:
===FILE: styles.css===
[complete CSS]
===END==="""

class UIDesignerInput:
    def __init__(self, *, build_id: str, project_name: str, requirement: str,
                 spec_summary: str, html_files: list[dict], css_plan_files: list[str],
                 fix_feedback: str = "", ui_layer: str = "html_css",
                 product_type: str = "web_app"):
        self.build_id = build_id
        self.project_name = project_name
        self.requirement = requirement
        self.spec_summary = spec_summary
        self.html_files = html_files
        self.css_plan_files = css_plan_files
        self.fix_feedback = fix_feedback
        self.ui_layer = ui_layer
        self.product_type = product_type


class UIDesignerOutput:
    def __init__(self, *, success: bool, generated_files: list[dict] = None, error: str = ""):
        self.success = success
        self.generated_files = generated_files or []
        self.error = error


class UIDesignerAgent(BaseAgent[UIDesignerInput, UIDesignerOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    # Structural fallback CSS — only layout/reset rules, NO color variables
    # Always goes AFTER LLM CSS so LLM colors always win
    STRUCTURAL_CSS = """
/* === Structural Fallbacks (layout only, no colors) === */
* { box-sizing: border-box; }
html, body { min-height: 100vh; font-family: 'Segoe UI', system-ui, sans-serif; line-height: 1.6; }
.navbar, nav { display: flex; align-items: center; padding: 0 2rem; height: 56px; position: sticky; top: 0; z-index: 100; }
.navbar a, nav a, .nav-link { text-decoration: none; padding: 0 1.25rem; height: 56px; display: flex; align-items: center; font-weight: 500; transition: all 0.2s; }
.container, main { max-width: 1200px; margin: 0 auto; padding: 2rem 1.5rem; }
.card { border-radius: 8px; padding: 1.5rem; transition: transform 0.2s; }
.btn, button { border: none; border-radius: 8px; padding: 0.5rem 1.25rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
input, select, textarea { border-radius: 8px; padding: 0.5rem 0.75rem; font-size: 0.875rem; width: 100%; }
.grid { display: grid; gap: 1rem; }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.flex { display: flex; gap: 1rem; align-items: center; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.tab-panel { display: none; } .tab-panel.active { display: block; }
.page { display: none; } .page.active { display: block; }
@media (max-width: 768px) { .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; } .navbar, nav { padding: 0 1rem; } .container, main { padding: 1rem; } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.fade-in { animation: fadeIn 0.3s ease; }
"""
    async def run(self, input_data: UIDesignerInput) -> UIDesignerOutput:
        import json, re as _re

        # Skip CSS generation for non-web projects
        if input_data.ui_layer not in ("html_css", "react", ""):
            logger.info("UI Designer: skipping — ui_layer is %s", input_data.ui_layer)
            return UIDesignerOutput(success=True, generated_files=[])

        src = self.build_dir / "src"
        src.mkdir(parents=True, exist_ok=True)

        # Read HTML files to understand what elements need styling
        html_summaries = []
        html_preview_lookup: dict[str, str] = {}
        for hf in input_data.html_files:
            preview = hf.get("content_preview", "") or hf.get("preview", "")
            if preview:
                fname = hf.get("relative_path", hf.get("path", ""))
                html_preview_lookup[fname] = preview

        for hf in input_data.html_files:
            rel = hf.get("path", hf.get("relative_path", "")).replace("src/", "")
            p = src / rel
            if p.exists():
                text = p.read_text(errors="replace")[:2000]
                html_summaries.append({"path": rel, "preview": text})
            elif rel in html_preview_lookup:
                html_summaries.append({"path": rel, "preview": html_preview_lookup[rel][:2000]})

        html_json = json.dumps(html_summaries, indent=2)
        css_list = json.dumps(["styles.css"], indent=2)

        feedback = ""
        if input_data.fix_feedback:
            feedback = f"\n\nFIX FEEDBACK:\n{input_data.fix_feedback}\n"

        prompt = (
            f"Project: {input_data.project_name}\n"
            f"Requirement: {input_data.requirement}\n"
            f"Spec Summary: {input_data.spec_summary}\n\n"
            f"HTML structure to style:\n{html_json}\n"
            f"{feedback}\n\n"
            f"Write a complete, beautiful styles.css for this project.\n"
            f"Look at the HTML elements and class names — style ALL of them.\n"
            f"The visual design must match what the user asked for in the requirement.\n"
            f"Include: CSS variables, body/background, navigation, headings, buttons, inputs, cards, tabs, forms, lists, responsive breakpoints.\n"
            f"Minimum 80 CSS rules. Make it look professional and polished.\n\n"
            "Output ONLY this format:\n"
            "===FILE: styles.css===\n"
            "[complete CSS]\n"
            "===END===\n"
            "No explanations. No markdown. Only the ===FILE: block."
        )

        response = await self.provider.complete(
            ModelRequest(
                prompt=prompt,
                system_prompt=load_system_prompt("ui_designer", _UI_DESIGNER_SYSTEM_DEFAULT),
                temperature=0.2,
                max_tokens=8192,
            )
        )
        if not response.success:
            return UIDesignerOutput(success=False, error=response.error)

        generated = self._parse_files(response.content, input_data.html_files)
        if not generated:
            # Fallback: try to extract any CSS blocks and write to styles.css
            fallback = self._extract_fallback_css(response.content, input_data.css_plan_files)
            if fallback:
                generated = fallback
            else:
                return UIDesignerOutput(
                    success=False,
                    error="No parseable CSS found. Model did not output /* FILE: name.css */ blocks."
                )

        # Validate: each CSS must have at least 50 chars (not empty)
        for g in generated:
            if g.get("size", 0) < 50:
                return UIDesignerOutput(
                    success=False,
                    error=f"CSS file {g['relative_path']} is too small ({g.get('size', 0)} chars). Must have real CSS rules."
                )

        return UIDesignerOutput(success=True, generated_files=generated)

    def _parse_files(self, raw: str, html_files: list[dict]) -> list[dict]:
        import re
        results = []

        # Method 1: Parse /* FILE: name.css */ inside ```css blocks
        css_blocks = re.findall(r'```css\s*(.*?)```', raw, re.DOTALL)
        for block in css_blocks:
            file_match = re.search(r'/\*\s*FILE:\s*([^\*/]+)\*/', block)
            if file_match:
                path = file_match.group(1).strip()
                body = re.sub(r'/\*\s*FILE:[^\*/]+\*/', '', block, count=1).strip()
            else:
                path = "styles.css"
                body = block.strip()
            rel_path = self._sanitize_path(path)
            if not rel_path:
                continue
            # Check if HTML files are in public/ subdirectory, write CSS there too
            if any("public/" in f.get("relative_path", "") for f in html_files):
                target = self.build_dir / "src" / "public" / Path(rel_path).name
                relative_path = f"src/public/{Path(rel_path).name}"
            else:
                target = self.build_dir / "src" / rel_path
                relative_path = f"src/{rel_path}"
            target.parent.mkdir(parents=True, exist_ok=True)
            merged = body + "\n\n" + self.STRUCTURAL_CSS
            # Quality check — enrich if LLM produced thin CSS
            if merged.count('{') < 20:
                logger.warning("UI Designer: thin CSS (%d rules) — enriching", merged.count('{'))
                merged = self._rich_fallback_css(input_data) + "\n\n" + body + "\n\n" + self.STRUCTURAL_CSS
            target.write_text(merged, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": relative_path,
                "size": len(body),
                "content_preview": body[:500],
            })

        # Method 2: Legacy ===FILE: path.css=== format
        if not results:
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
                merged = body + "\n\n" + self.STRUCTURAL_CSS
                target.write_text(merged, encoding="utf-8")
                results.append({
                    "path": str(target),
                    "relative_path": f"src/{rel_path}",
                    "size": len(body),
                    "content_preview": body[:500],
                })

        if results:
            logger.info("UI Designer parsed %d files from %d characters", len(results), len(raw))
        return results

    def _rich_fallback_css(self, input_data) -> str:
        """Generate rich guaranteed CSS when LLM output is too thin."""
        req = (input_data.requirement or "").lower()

        # Detect colors from requirement
        color_map = {
            "red": "#dc2626", "green": "#16a34a", "blue": "#2563eb",
            "pink": "#db2777", "purple": "#9333ea", "orange": "#ea580c",
            "yellow": "#ca8a04", "teal": "#0d9488", "cyan": "#0891b2",
        }
        detected = [(n, h) for n, h in color_map.items() if n in req]
        is_dark = any(w in req for w in ["dark", "night", "black", "neon", "cyber"])
        is_light = any(w in req for w in ["light", "bright", "white", "clean"])

        if is_dark:
            bg, surface, card, text, muted, border = "#0f1117","#1a1d2e","#1e2235","#e2e8f0","#94a3b8","#2a2d3e"
            accent = detected[0][1] if detected else "#00d4aa"
        elif detected:
            accent = detected[0][1]
            bg, surface, card, text, muted, border = "#f8fafc","#ffffff","#ffffff","#1e293b","#64748b","#e2e8f0"
        else:
            bg, surface, card, text, muted, border = "#f8fafc","#ffffff","#ffffff","#1e293b","#64748b","#e2e8f0"
            accent = "#6366f1"

        # Build per-color tab classes
        tab_colors = "\n".join([
            f".tab-{n}, button[data-tab*='{n}'], .{n}-tab {{ background: {h} !important; color: white !important; border-color: {h} !important; }}"
            for n, h in detected
        ]) if detected else ""

        return f"""/* === Rich Fallback CSS (UI Designer enrichment) === */
:root {{
  --bg: {bg}; --surface: {surface}; --card: {card};
  --accent: {accent}; --accent-hover: color-mix(in srgb, {accent} 80%, black);
  --text: {text}; --muted: {muted}; --border: {border};
  --radius: 8px; --shadow: 0 2px 8px rgba(0,0,0,0.12);
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; line-height: 1.6; min-height: 100vh; }}
h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }}
h2 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; }}
h3 {{ font-size: 1.1rem; font-weight: 600; }}
p {{ color: var(--muted); }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
nav, .navbar {{ display: flex; align-items: center; gap: 1rem; background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 2rem; position: sticky; top: 0; z-index: 100; box-shadow: var(--shadow); }}
nav a, .nav-link {{ color: var(--muted); padding: 0.5rem 0.75rem; border-radius: var(--radius); font-weight: 500; transition: all 0.2s; }}
nav a:hover, .nav-link:hover, nav a.active, .nav-link.active {{ color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); text-decoration: none; }}
.container, main {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; box-shadow: var(--shadow); margin-bottom: 1rem; }}
.card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.15); transform: translateY(-1px); transition: all 0.2s; }}
button, .btn {{ background: var(--accent); color: white; border: none; border-radius: var(--radius); padding: 0.6rem 1.25rem; font-weight: 600; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.4rem; }}
button:hover, .btn:hover {{ background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
button:active, .btn:active {{ transform: translateY(0); }}
input, select, textarea {{ background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.6rem 0.9rem; font-size: 0.9rem; width: 100%; font-family: inherit; transition: border-color 0.2s, box-shadow 0.2s; }}
input:focus, select:focus, textarea:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent); }}
label {{ font-size: 0.85rem; font-weight: 500; color: var(--muted); display: block; margin-bottom: 0.3rem; }}
.tab-btn, .nav-tab {{ background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.6rem 1.25rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
.tab-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.tab-btn.active {{ background: var(--accent); color: white; border-color: var(--accent); box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 40%, transparent); }}
.tab-panel {{ display: none; padding-top: 1.5rem; animation: fadeIn 0.2s ease; }}
.tab-panel.active {{ display: block; }}
.tabs, .tab-nav {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: var(--surface); color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.75rem 1rem; text-align: left; border-bottom: 2px solid var(--border); }}
td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }}
tr:hover td {{ background: color-mix(in srgb, var(--accent) 5%, transparent); }}
ul, ol {{ padding-left: 1.5rem; color: var(--muted); }}
li {{ margin-bottom: 0.4rem; }}
.grid-2 {{ display: grid; grid-template-columns: repeat(2,1fr); gap: 1rem; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 1rem; }}
.flex {{ display: flex; gap: 1rem; align-items: center; }}
.flex-between {{ display: flex; justify-content: space-between; align-items: center; }}
.badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.75rem; font-weight: 600; background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); }}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@media (max-width: 768px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} nav, .navbar {{ padding: 0.75rem 1rem; flex-wrap: wrap; }} .container, main {{ padding: 1rem; }} }}
{tab_colors}
"""

    def _extract_fallback_css(self, raw: str, planned_files: list[str]) -> list[dict]:
        import re
        results = []
        # Extract any ```css block without FILE header
        blocks = re.findall(r'```css\s*(.*?)```', raw, re.DOTALL)
        if not blocks:
            # Try without language tag
            blocks = re.findall(r'```\s*(.*?)```', raw, re.DOTALL)
        for i, body in enumerate(blocks):
            body = body.strip()
            if len(body) < 50:
                continue
            path = planned_files[i] if i < len(planned_files) else "styles.css"
            rel_path = self._sanitize_path(path)
            if not rel_path:
                rel_path = "styles.css"
            
            # Check if HTML files are in public/ subdirectory, write CSS there too
            # Note: We need to detect HTML file location here too
            src = self.build_dir / "src"
            html_files_in_public = False
            for html_file in src.rglob("*.html"):
                if "public/" in str(html_file.relative_to(src)):
                    html_files_in_public = True
                    break
            
            if html_files_in_public:
                target = self.build_dir / "src" / "public" / Path(rel_path).name
                relative_path = f"src/public/{Path(rel_path).name}"
            else:
                target = self.build_dir / "src" / rel_path
                relative_path = f"src/{rel_path}"
            
            target.parent.mkdir(parents=True, exist_ok=True)
            merged = body + "\n\n" + self.STRUCTURAL_CSS
            # Quality check — enrich if LLM produced thin CSS
            if merged.count('{') < 20:
                logger.warning("UI Designer: thin CSS (%d rules) — enriching", merged.count('{'))
                merged = self._rich_fallback_css(input_data) + "\n\n" + body + "\n\n" + self.STRUCTURAL_CSS
            target.write_text(merged, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": relative_path,
                "size": len(body),
                "content_preview": body[:500],
            })
        if results:
            logger.info("UI Designer fallback extracted %d CSS blocks", len(results))
        return results

    def _sanitize_path(self, raw: str) -> str:
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:]
        raw = raw.lstrip("/\\")
        if raw.lower().startswith("src/") or raw.lower().startswith("src\\"):
            raw = raw[4:]
            raw = raw.lstrip("/\\")
        parts = raw.replace("\\", "/").split("/")
        safe = [p for p in parts if p and p != "." and p != ".."]
        if not safe:
            return ""
        joined = "/".join(safe)
        test = (self.build_dir / "src" / joined).resolve()
        src_root = (self.build_dir / "src").resolve()
        try:
            test.relative_to(src_root)
        except ValueError:
            logger.warning("Rejected path-traversal attempt: %s", raw)
            return ""
        return joined
