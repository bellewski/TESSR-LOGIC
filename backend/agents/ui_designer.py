import logging
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)


_UI_DESIGNER_SYSTEM_DEFAULT = """You are a world-class UI/UX designer. Write ONE complete styles.css.

READ THE REQUIREMENT. The user tells you what this app looks like.
- "pink" = pink colors. "dark" = dark theme. "colorful tabs" = each tab a different color.
- "game" = exciting dark neon. "professional" = clean corporate. "bright" = light vibrant.
- No style specified = clean modern dark theme (#0f1117 background).

Output ONLY:
===FILE: styles.css===
[your CSS here]
===END===

REQUIRED SECTIONS:
1. :root with --bg, --surface, --card, --accent, --text, --muted, --border
2. * reset, html/body
3. .navbar/nav with sticky positioning
4. .nav-link hover + active states
5. h1 h2 h3 typography
6. .container max-width layout
7. .btn with hover transform + shadow
8. input select textarea with focus glow
9. .card with hover lift
10. .tab-btn .tab-panel tab switching
11. .tab-red .tab-green .tab-blue .tab-purple .tab-orange (colored variants)
12. @media mobile responsive

FOR MULTI-COLOR TABS: give each color its own class with matching background, glow on active.
MINIMUM 60 rules, 150 lines. Real CSS only."""

class UIDesignerInput:
    def __init__(self, *, build_id: str, project_name: str, requirement: str,
                 spec_summary: str, html_files: list[dict], css_plan_files: list[str],
                 fix_feedback: str = ""):
        self.build_id = build_id
        self.project_name = project_name
        self.requirement = requirement
        self.spec_summary = spec_summary
        self.html_files = html_files
        self.css_plan_files = css_plan_files
        self.fix_feedback = fix_feedback


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

        src = self.build_dir / "src"
        src.mkdir(parents=True, exist_ok=True)

        # Step 0: Write structural base CSS — layout only, NO colors
        # The LLM will generate all colors/theme based on the requirement
        structural_css = self.STRUCTURAL_CSS
        
        css_locations = []
        for html_file in src.rglob("*.html"):
            css_path = html_file.parent / "styles.css"
            if css_path not in css_locations:
                css_locations.append(css_path)
        if not css_locations:
            css_locations = [src / "styles.css"]
        for css_path in css_locations:
            css_path.write_text(structural_css, encoding="utf-8")
            logger.info("UI Designer: wrote structural base CSS to %s", css_path)

        # The LLM generates all visual styling — colors, theme, tabs, etc.
        # based entirely on the requirement. No Python color detection.
        # Theme CSS is now on disk as a guaranteed base.
        # Now call the 70b LLM to enhance it with requirement-specific styling.
        # Read existing HTML to understand structure -- use disk content, fallback to coder preview
        html_summaries = []
        src = self.build_dir / "src"
        # Build a lookup of coder content previews by filename for fallback
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
                text = p.read_text(errors="replace")[:1500]
                html_summaries.append({"path": rel, "preview": text})
            elif rel in html_preview_lookup:
                html_summaries.append({"path": rel, "preview": html_preview_lookup[rel][:1500]})

        # Force only styles.css generation regardless of plan
        css_list = json.dumps(["styles.css"], indent=2)
        html_json = json.dumps(html_summaries, indent=2)

        feedback = ""
        if input_data.fix_feedback:
            feedback = f"\n\nFIX FEEDBACK:\n{input_data.fix_feedback}\n"

        prompt = (
            f"Project: {input_data.project_name}\n"
            f"Requirement: {input_data.requirement[:500]}\n"
            f"Spec Summary: {input_data.spec_summary}\n\n"
            f"CSS files to generate: {css_list}\n\n"
            f"Existing HTML structure:\n{html_json}\n"
            f"{feedback}\n\n"
            "Generate ONLY styles.css now inside a markdown ```css block. "
            "Start with /* FILE: styles.css */. "
            "NO explanations. ONLY CSS code."
        )

        response = await self.provider.complete(
            ModelRequest(
                prompt=prompt,
                system_prompt=load_system_prompt("ui_designer", _UI_DESIGNER_SYSTEM_DEFAULT),
                temperature=0.15,
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
