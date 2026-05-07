import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are an expert software engineer. Generate source code files from the file_plan.

STACK-SPECIFIC REQUIREMENTS (CRITICAL):
- IF STACK IS "HTML5" OR "VANILLA": NEVER use React, JSX, Vue, Angular, or any framework. ONLY plain HTML, CSS, vanilla JavaScript
- IF STACK IS "HTML5": NO import statements, NO JSX syntax, NO React components, NO build tools
- IF STACK IS "HTML5": Use document.createElement, addEventListener, querySelector - ONLY vanilla DOM APIs
- IF STACK IS "HTML5": All JavaScript must run directly in browsers without compilation

OUTPUT FORMAT - ONLY file blocks in this exact format, NOTHING ELSE:
===FILE: relative/path.ext===
<code here>
===END===

CRITICAL RULES (violating any = FAILURE):
1. Every file must be COMPLETE working code. NO stubs, NO TODOs, NO placeholders like "// TO DO: implement".
2. Every HTML file must be a full document with DOCTYPE, html, head, body.
3. Every HTML page MUST have: <main> content sections, <footer>. For dashboard/single-page apps: NO navigation to other pages - use sections/tabs within one page. For multi-page apps: <nav> with links to ALL other HTML pages.
4. Every HTML links ONLY to styles.css and app.js: <link rel="stylesheet" href="../styles.css"> and <script src="app.js"></script>. For HTML in subdirectories, use ../styles.css for CSS.
5. There is EXACTLY ONE styles.css shared by ALL pages. NEVER create per-page CSS (no game.css, plants.css, etc.).
6. There is EXACTLY ONE app.js shared by ALL pages plus ONE data.js if needed. NEVER create per-page JS.
7. All HTML uses RELATIVE paths only: href="page.html" src="app.js" href="styles.css".
8. DASHBOARD/SINGLE-PAGE APPS: Use ONE index.html with tabbed sections (Registration, Login, Verification, MFA, Recovery). NO separate HTML files. Use JavaScript to show/hide sections. ALL files go in src/public/ or src/ root, NOT in subdirectories.
9. BLOCKCHAIN IDENTITY: Generate professional security dashboard with registration forms, login interfaces, blockchain verification status, MFA setup, and recovery processes. NO generic "test page" content.
10. CSS classes must be descriptive: .hero .card .navbar .btn-primary .section-title .grid-container.
11. JS MUST use addEventListener for ALL buttons/interactive elements. MUST manipulate DOM.
12. Data must be REALISTIC: real names, real descriptions, real numbers. NEVER "Lorem ipsum" or "sample data".
13. STACK COMPLIANCE: NEVER use React/JSX/Vue/Angular when HTML5/vanilla specified. Use ONLY vanilla JavaScript.
14. NEVER output .jsx or .tsx files. ONLY .html, .css, .js files allowed.
15. NEVER use React class components, JSX syntax, or import statements.
16. If fix feedback was provided, address EVERY issue listed. Rewrite affected files completely.
17. NEVER generate the same file twice. Check your output before responding.

DONE_WHEN: response contains ONLY ===FILE: path.ext=== ... ===END=== blocks. NO markdown, NO explanations, NO extra text. Every file_plan file generated. All code is real and working.

OUTPUT FORMAT IS ABSOLUTE - NO EXCEPTIONS:
===FILE: filename.ext===
<code here>
===END===
REPEAT FOR EACH FILE. NO OTHER TEXT ALLOWED."""

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

        # Filter out CSS files - UI Designer handles CSS exclusively
        file_plan = [f for f in file_plan if not f.get("path", "").endswith(".css")]
        if not file_plan:
            return CoderOutput(success=True, generated_files=[], error="No non-CSS files to generate (CSS handled by Designer)")

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

        # Batch files into chunks of 2 so 13B models can generate within timeout
        BATCH_SIZE = 2
        batches = [
            file_plan[i : i + BATCH_SIZE]
            for i in range(0, len(file_plan), BATCH_SIZE)
        ]

        for batch_idx, batch in enumerate(batches):
            batch_json = json.dumps(batch, indent=2)
            prior_files = json.dumps([f["path"] for f in all_generated], indent=2) if all_generated else "none yet"

            stack_warning = ""
            if input_data.stack_target.lower() in ["html5", "vanilla", "plain"]:
                stack_warning = "\n\n!!! CRITICAL: STACK IS HTML5/VANILLA - NO FRAMEWORKS ALLOWED !!!\nNEVER use React, JSX, Vue, Angular, imports, or any build tools.\nONLY plain HTML, CSS, and vanilla JavaScript with DOM APIs.\n"
            
            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target}{stack_warning}\n"
                f"Requirement:\n{input_data.requirement}\n\n"
                f"Spec Summary:\n{input_data.spec_summary}\n\n"
                f"Files already generated: {prior_files}\n\n"
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
