import logging
from pathlib import Path

from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

_UI_DESIGNER_SYSTEM_DEFAULT = """You are a world-class UI Designer agent. Your ONLY job is to write PROFESSIONAL, PRODUCTION-READY CSS files that create visually stunning websites.

FILE RULES (non-negotiable):
- You MUST generate EXACTLY ONE CSS file named styles.css. NEVER create per-page CSS files like mouse-catcher.css, app.css, contact.css, etc.
- ALL styles for every page MUST be in the single styles.css file.

QUALITY STANDARDS (non-negotiable):
1. CSS MUST have 30+ selectors with real properties. NO stubs, NO empty rules.
2. Use CSS variables in :root for colors, spacing, fonts, shadows, border-radius.
3. Create a MODERN color palette with primary, secondary, accent, success, warning, danger colors.
4. Dark mode: html[data-theme="dark"] selector with COMPLETE color inversions.
5. Responsive: @media (max-width: 768px) AND @media (max-width: 480px).
6. Flexbox AND Grid layouts — not just basic block display.
7. Hover/focus/active states for ALL interactive elements with transitions.
8. Box shadows, border-radius, gradients for visual depth.
9. Smooth transitions: transition: all 0.3s ease for interactive elements.
10. Typography hierarchy: h1-h6 with distinct sizes, weights, line-heights.
11. Card components with hover lift effects (transform: translateY, box-shadow).
12. Gradient backgrounds for hero sections.
13. Sticky/fixed navigation with backdrop blur.
14. Animated elements: keyframes for fade-in, slide-up, pulse.

BLOCKCHAIN IDENTITY STYLING:
15. Security-focused design: trust badges, verification status indicators, secure form styling
16. Professional color scheme: blues/greens for security, proper contrast for accessibility
17. Form validation styles: error states, success states, loading indicators
18. Tab/section navigation: clear active states, smooth transitions between sections
19. Status indicators: blockchain sync status, verification progress, security level indicators

OUTPUT FORMAT — USE EXACTLY THIS:
```css
/* FILE: styles.css */
:root {
  --primary: #6366f1;
  --primary-dark: #4f46e5;
  --secondary: #ec4899;
  --accent: #06b6d4;
  --bg: #f8fafc;
  --bg-alt: #f1f5f9;
  --text: #0f172a;
  --text-muted: #64748b;
  --card-bg: #ffffff;
  --card-border: #e2e8f0;
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  --radius: 0.75rem;
  --radius-sm: 0.375rem;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}

.container { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem; }

.navbar {
  position: sticky;
  top: 0;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--card-border);
  padding: 1rem 0;
  z-index: 100;
}

.nav-links { display: flex; gap: 2rem; list-style: none; }
.nav-links a { text-decoration: none; color: var(--text); font-weight: 500; transition: color 0.2s; }
.nav-links a:hover, .nav-links a.active { color: var(--primary); }

.hero {
  background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
  color: white;
  padding: 6rem 0;
  text-align: center;
}
.hero h1 { font-size: 3.5rem; font-weight: 800; margin-bottom: 1rem; }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 2rem;
  border-radius: var(--radius);
  font-weight: 600;
  text-decoration: none;
  border: none;
  cursor: pointer;
  transition: all 0.3s ease;
}
.btn-primary { background: var(--primary); color: white; box-shadow: var(--shadow); }
.btn-primary:hover { background: var(--primary-dark); transform: translateY(-2px); box-shadow: var(--shadow-lg); }

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--radius);
  padding: 1.5rem;
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
}
.card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg); }

.grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; }

.stats-bar { display: flex; justify-content: center; gap: 4rem; padding: 3rem 0; background: var(--bg-alt); }
.stat { text-align: center; }
.stat-number { display: block; font-size: 2.5rem; font-weight: 800; color: var(--primary); }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-in { animation: fadeInUp 0.6s ease forwards; }

html[data-theme="dark"] {
  --bg: #0f172a;
  --bg-alt: #1e293b;
  --text: #f8fafc;
  --text-muted: #94a3b8;
  --card-bg: #1e293b;
  --card-border: #334155;
}
html[data-theme="dark"] .navbar { background: rgba(15,23,42,0.9); }

@media (max-width: 768px) {
  .hero h1 { font-size: 2rem; }
  .nav-links { display: none; }
  .stats-bar { flex-direction: column; gap: 1.5rem; }
  .grid-container { grid-template-columns: 1fr; }
}
```

RULES:
1. Output each CSS file inside a markdown ```css block. Start the block with /* FILE: filename.css */.
2. CSS MUST have 30+ selectors with real properties. NO stubs.
3. CSS variables in :root for colors, spacing, fonts, shadows, border-radius.
4. Dark mode: html[data-theme="dark"] selector overrides.
5. Responsive: @media (max-width: 768px) AND @media (max-width: 480px).
6. Flexbox/Grid for layout.
7. Hover/focus/active states with transitions for interactive elements.
8. NO explanations outside code blocks. ONLY CSS code.
9. Include .btn, .card, .nav, .container, .hero, .grid-container, .stats-bar utility classes.
10. Use box-shadow, border-radius, gradients for visual depth.
11. Include @keyframes animations for fade-in, slide-up effects.
12. Sticky nav with backdrop-filter blur.
"""


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

        # Read existing HTML to understand structure
        html_summaries = []
        src = self.build_dir / "src"
        for hf in input_data.html_files:
            p = src / hf.get("path", "").replace("src/", "")
            if p.exists():
                text = p.read_text(errors="replace")[:800]
                html_summaries.append({"path": hf.get("path", ""), "preview": text})

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
