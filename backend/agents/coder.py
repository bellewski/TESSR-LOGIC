import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are a world-class full-stack software engineer. 
You can build ANY type of application perfectly from a clear requirement.

STRICT RULES:
- Always generate complete, production-quality, fully functional code.
- For HTML5 projects: produce exactly `index.html`, `styles.css`, `app.js` 
- index.html = full valid document with modern dark theme
- styles.css = rich, beautiful, responsive CSS
- app.js = complete interactivity using addEventListener, localStorage, dynamic rendering, modals, etc.
- NEVER output placeholders, TODOs, or minimal code.
- Make EVERY requested feature actually work.

CRITICAL HTML REQUIREMENT:
- EVERY HTML file MUST have <link rel="stylesheet" href="styles.css"> in the <head>
- EVERY HTML file MUST have <script src="app.js" defer></script> before </body>
- Multi-page apps: ALL pages link the SAME styles.css and app.js
- Navigation links between pages MUST use relative paths (e.g. href="dashboard.html")
- ALL nav links must be <a href="pagename.html"> — never href="#" for navigation

CRITICAL FUNCTIONALITY REQUIREMENTS:
- ALL buttons must have working addEventListener handlers
- ALL images must use reliable sources (picsum.photos, unsplash.it, cataas.com)
- NO broken images or non-functional buttons
- Complete UI with all requested sections and features
- Real data persistence with localStorage
- Smooth animations and transitions

Output format ONLY:
===FILE: filename===
code
===END===
"""

class CoderInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    stack_target: str
    spec_summary: str
    file_plan: list[dict]
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
            
            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target}{stack_warning}\n"
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
        # This runs after all batches so the UI Designer's CSS is always picked up
        src_dir = self.build_dir / "src"
        if src_dir.exists():
            for html_file in src_dir.rglob("*.html"):
                try:
                    content = html_file.read_text(encoding="utf-8")
                    # Only inject if no stylesheet link exists at all
                    if "styles.css" not in content and "<link" not in content.lower():
                        inject = '<link rel="stylesheet" href="styles.css">'
                        if "</head>" in content:
                            content = content.replace("</head>", f"  {inject}\n</head>")
                        elif "<head>" in content:
                            content = content.replace("<head>", f"<head>\n  {inject}")
                        html_file.write_text(content, encoding="utf-8")
                        logger.info("Coder: injected styles.css link into %s", html_file.name)
                        # Update the generated_files entry with new content
                        for f in all_generated:
                            if f.get("path") == str(html_file):
                                f["content_preview"] = content[:500]
                                f["size"] = len(content)
                except Exception as e:
                    logger.warning("Could not inject stylesheet into %s: %s", html_file.name, e)

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
