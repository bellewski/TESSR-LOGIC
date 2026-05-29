import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

_VALIDATOR_SYSTEM_DEFAULT = """You are a code quality validator. You check if the build actually does what the user asked for.

Your job: read the requirement, look at the generated files, decide if it's done.

CHECK FOR:
- Does the HTML have the UI elements the user asked for? (tabs, forms, cards, colors)
- Does the JS implement the interactions? (add/delete, tab switching, form handling)
- Are all pages/sections from the requirement present?
- Is the visual theme/color scheme as requested?

PASS if the core requirement is implemented, even if imperfect.
FAIL if major features are missing or the wrong thing was built entirely.

Be pragmatic — a working app with minor issues should PASS. Only fail if fundamentally broken.

Respond ONLY with valid JSON:
{"passed": true|false, "confidence": 0-100, "issues": ["specific missing features"], "fix_feedback": "what exactly to add/fix"}"""

VALIDATOR_SYSTEM = _VALIDATOR_SYSTEM_DEFAULT  # kept for backward compat


class ValidatorInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    generated_files: list[dict]
    findings: list[dict]
    build_dir: str
    file_plan: list[dict] = []  # from Architect — used to detect missing planned files


class ValidatorOutput(BaseModel):
    success: bool
    error: str = ""
    passed: bool = False
    confidence: int = 0
    issues: list[str] = []
    fix_feedback: str = ""


class ValidatorAgent(BaseAgent[ValidatorInput, ValidatorOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: ValidatorInput) -> ValidatorOutput:
        import json

        # Check final files after FileConsolidation, not intermediate generated files
        final_files = self._get_final_files()
        files_exist = self._check_final_files_complete(final_files, input_data.requirement)

        if not files_exist["ok"]:
            return ValidatorOutput(
                success=True,
                passed=False,
                confidence=0,
                issues=[f"Missing files: {files_exist['missing']}"],
                fix_feedback=f"The following required files are missing: {files_exist['missing']}. Please create them.",
            )

        # Check planned files vs actually generated files
        if input_data.file_plan:
            generated_names = {Path(f.get("path", "")).name for f in final_files}
            planned_names = {Path(f.get("path", "")).name for f in input_data.file_plan if f.get("type") == "source"}
            missing_planned = planned_names - generated_names
            # Only flag HTML files as critical — CSS/JS can be consolidated
            missing_html = {n for n in missing_planned if n.endswith(".html")}
            if missing_html:
                missing_list = ", ".join(sorted(missing_html))
                return ValidatorOutput(
                    success=True,
                    passed=False,
                    confidence=20,
                    issues=[f"Missing planned HTML files: {missing_list}"],
                    fix_feedback=(
                        f"The Architect planned these HTML files but they were not generated: {missing_list}. "
                        f"You MUST generate ALL planned pages. Create each missing HTML file with full content."
                    ),
                )

        # Rule-based pre-checks — catch obvious failures before wasting an LLM call
        import re as _re
        from pathlib import Path as _Path
        rule_issues = []
        rule_feedback = []

        for f in final_files:
            fname = _Path(f.get("path", "")).name
            preview = f.get("content_preview", "")
            if not fname.endswith(".html") or not preview:
                continue
            # Check for empty shell / comment-only HTML
            is_empty_shell = (
                _re.search(r'<div\s+id=["\']app["\']>\s*<\/div>', preview, _re.IGNORECASE) or
                _re.search(r'<body[^>]*>\s*<script', preview, _re.IGNORECASE) or
                (_re.search(r'<(section|div|main)[^>]*>\s*<!--', preview, _re.IGNORECASE) and
                 len(_re.findall(r'<(input|button|select|table|form|ul|ol)', preview, _re.IGNORECASE)) == 0)
            )
            if is_empty_shell:
                rule_issues.append(f"{fname}: HTML is an empty shell — no real DOM elements in preview")
                rule_feedback.append(
                    f"{fname}: You generated an empty shell <div id='app'></div> or comment-only HTML. "
                    f"You MUST write ALL content directly in HTML. Every section needs real <div class='card'>, "
                    f"<nav class='navbar'>, <button class='btn'>, <input>, <table> elements. "
                    f"Do NOT render content from JavaScript — put it in HTML."
                )

        if rule_issues:
            return ValidatorOutput(
                success=True,
                passed=False,
                confidence=10,
                issues=rule_issues,
                fix_feedback="\n".join(rule_feedback),
            )

        # Build file summary with actual final files after FileConsolidation
        final_files = self._get_final_files()
        file_summary = []
        for f in final_files:
            entry = {
                "path": f.get("relative_path", str(f.get("path", ""))),
                "size_bytes": f.get("size_bytes", f.get("size", 0)),
            }
            metrics = f.get("quality_metrics")
            if metrics:
                entry["quality_metrics"] = metrics
            preview = f.get("content_preview", "")
            if preview:
                entry["preview"] = preview[:400]
            file_summary.append(entry)

        high_findings = [f for f in input_data.findings if f.get("severity") == "high"]

        prompt = (
            f"Project: {input_data.project_name}\n"
            f"Requirement Summary: {input_data.requirement[:500]}\n\n"
            f"Generated files ({len(file_summary)} total):\n{json.dumps(file_summary, indent=2)}\n\n"
            f"High severity findings ({len(high_findings)}):\n{json.dumps(high_findings[:10], indent=2)}\n\n"
            "Validate the build completeness and quality now."
        )

        response = await self.provider.complete(
            ModelRequest(prompt=prompt, system_prompt=load_system_prompt("validator", _VALIDATOR_SYSTEM_DEFAULT), temperature=0.2, max_tokens=1024)
        )

        if not response.success:
            logger.error("Validator LLM call failed: %s", response.error)
            return ValidatorOutput(
                success=True,
                passed=False,
                confidence=0,
                issues=["Validator LLM unavailable — cannot assess functional completeness"],
                fix_feedback="Validator was unable to check spec compliance due to LLM error. Please verify all required functionality is implemented.",
            )

        try:
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            data = json.loads(content)
            return ValidatorOutput(
                success=True,
                passed=data.get("passed", False),
                confidence=data.get("confidence", 0),
                issues=data.get("issues", []),
                fix_feedback=data.get("fix_feedback", ""),
            )
        except Exception as e:
            logger.error("Validator JSON parse failed: %s", e)
            return ValidatorOutput(
                success=True,
                passed=False,
                confidence=0,
                issues=["Could not parse validator LLM response"],
                fix_feedback=f"Validator produced unparseable output. Raw response: {response.content[:800]}",
            )

    def _get_final_files(self) -> list[dict]:
        """Get final files that actually exist after FileConsolidation"""
        src_dir = self.build_dir / "src"
        if not src_dir.exists():
            return []
        
        final_files = []
        for file_path in src_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(src_dir)  # Relative to src, not build_dir
                size_bytes = file_path.stat().st_size
                
                # Generate richer content preview + quality metrics for text files
                content_preview = ""
                quality_metrics: dict = {}
                try:
                    if file_path.suffix in ['.html', '.css', '.js', '.json', '.md', '.txt']:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            full_text = f.read()
                        content_preview = full_text[:1000]
                        # Add structural metrics so LLM has signal beyond raw preview
                        if file_path.suffix == '.html':
                            import re
                            quality_metrics = {
                                "element_count": len(re.findall(r'<[a-zA-Z]', full_text)),
                                "has_doctype": '<!doctype' in full_text.lower(),
                                "has_body": '<body' in full_text.lower(),
                                "has_script": '<script' in full_text.lower(),
                            }
                        elif file_path.suffix == '.css':
                            quality_metrics = {
                                "rule_count": full_text.count('}'),
                                "has_variables": '--' in full_text,
                                "has_media_queries": '@media' in full_text,
                                "selector_count": full_text.count('{'),
                            }
                        elif file_path.suffix == '.js':
                            quality_metrics = {
                                "function_count": full_text.count('function ') + full_text.count('=>'),
                                "has_event_listeners": 'addEventListener' in full_text,
                                "has_dom_queries": 'querySelector' in full_text or 'getElementById' in full_text,
                                "line_count": full_text.count('\n'),
                            }
                except Exception:
                    content_preview = ""
                    quality_metrics = {}
                
                final_files.append({
                    "path": str(file_path),
                    "relative_path": str(relative_path),
                    "name": file_path.name,
                    "size": size_bytes,
                    "size_bytes": size_bytes,
                    "content_preview": content_preview,
                    "quality_metrics": quality_metrics,
                })
        return final_files

    def _check_final_files_complete(self, final_files: list[dict], requirement: str) -> dict:
        """Check if final files meet basic requirements after consolidation"""
        missing = []
        
        # Check for at least one HTML file
        html_files = [f for f in final_files if f["name"].lower().endswith('.html')]
        if not html_files:
            missing.append("index.html")
        
        # Check for at least one CSS file (prefer styles.css but allow any CSS)
        css_files = [f for f in final_files if f["name"].lower().endswith('.css')]
        if not css_files:
            missing.append("styles.css (or any CSS file)")
        
        # Check for at least one JS file
        js_files = [f for f in final_files if f["name"].lower().endswith('.js')]
        if not js_files:
            missing.append("app.js")
        
        return {"ok": len(missing) == 0, "missing": missing}

    def _check_files_exist(self, generated_files: list[dict]) -> dict:
        missing = []
        for f in generated_files:
            path = Path(f.get("path", ""))
            if not path.exists():
                missing.append(f.get("relative_path", str(path)))
        return {"ok": len(missing) == 0, "missing": missing}
