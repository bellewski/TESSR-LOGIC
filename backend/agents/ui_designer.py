import logging
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)


_UI_DESIGNER_SYSTEM_DEFAULT = """You are a world-class UI/UX designer. Your job is to produce ONE complete, stunning styles.css file.

CRITICAL OUTPUT RULE:
Output ONLY this exact format -- nothing else:
===FILE: styles.css===
/* your complete CSS here */
===END===

DESIGN REQUIREMENTS (non-negotiable):
- Dark theme: background #0f1117, surface #1a1d2e, cards #1e2235
- Accent color: #00d4aa (teal/cyan) with hover #00b894
- Text: #e2e8f0 primary, #94a3b8 muted
- Every element must be styled -- no browser-default unstyled elements
- Navigation: horizontal nav bar or sidebar with styled links, hover states, active state
- Buttons: colored background, rounded corners, hover transition, cursor pointer
- Inputs/selects: dark background, styled border, focus glow
- Cards/sections: background surface color, border, border-radius 8px, padding
- Typography: clean font stack, proper heading sizes, line-height
- Responsive: mobile breakpoints with @media queries
- Animations: smooth transitions on hover (0.2s), subtle entrance animations
- CSS variables at :root for all colors

MANDATORY CSS SECTIONS (include ALL of these):
1. :root variables
2. * reset (box-sizing, margin, padding)
3. body (background, color, font)
4. nav / .navbar (full navigation styling)
5. a, nav a (link colors, hover, active states)
6. h1, h2, h3 (heading styles)
7. .container / main (max-width, padding, layout)
8. button, .btn (full button styling with hover)
9. input, select, textarea (form element styling)
10. .card / section (card/panel styling)
11. table / .table (if data tables are used)
12. @media queries (mobile responsive)

QUALITY STANDARDS:
- CSS MUST have 30+ selectors with real properties
- Use CSS variables in :root for all colors
- Flexbox AND Grid layouts
- Hover/focus/active states for ALL interactive elements
- Box shadows, border-radius, gradients for visual depth
- Typography hierarchy with distinct heading sizes
- Card components with hover lift effects
- Sticky navigation with backdrop blur
- Keyframe animations for fade-in, slide-up

MINIMUM: 80 CSS rules. At least 200 lines of real CSS.
NO placeholders. NO TODOs. Complete production CSS only."""

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

    async def run(self, input_data: UIDesignerInput) -> UIDesignerOutput:
        import json

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
            target.write_text(body, encoding="utf-8")
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
                target.write_text(body, encoding="utf-8")
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
            target.write_text(body, encoding="utf-8")
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
