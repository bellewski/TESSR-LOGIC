import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

_VALIDATOR_SYSTEM_DEFAULT = """You are a QA engineer. Check if the build actually implements what was specified.

Read the spec_summary and the generated files. Ask: does this build do what was asked?

Check specifically:
- Are all the features from the spec present in the code?
- Does the interactive logic actually work? (event handlers, game loops, form processing)
- Are all the entities/characters/items/pages from the spec implemented?
- Does the data persistence exist?
- Is the visual design consistent with what was requested?

Judge ONLY against what the spec/requirement actually asks for:
- Do NOT invent or demand requirements that were not requested — NO unit tests, build
  tooling, frameworks, accessibility audits, or extra features unless the spec asked for them.
- If a feature appears implemented in the provided code/preview (e.g. you can see
  localStorage calls, event handlers, the relevant functions), treat it as PRESENT — do
  not repeatedly demand something that is already there.
- Do not re-raise the same issue you raised before if the code already addresses it.

Be strict but fair:
- PASS if the core functionality from the spec is implemented even if minor details are missing
- FAIL only if MAJOR spec features are absent or the logic is clearly broken
- FAIL if it looks like a stub — bare HTML with no real content
- Confidence 0-100 reflecting how complete the implementation is vs. the spec (not vs. an ideal)

Respond ONLY with valid JSON:
{"passed": true|false, "confidence": 0-100, "issues": ["specific missing things"], "fix_feedback": "precise instructions: what to add and how"}"""



class ValidatorInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    generated_files: list[dict]
    findings: list[dict]
    build_dir: str
    file_plan: list[dict] = []
    contract: dict = {}  # Architect's contract — drives what "complete" means


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
        files_exist = self._check_final_files_complete(final_files, input_data.requirement, input_data.contract)

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

        contract = input_data.contract or {}
        ui_layer = contract.get("ui_layer", "html_css")
        stack_family = contract.get("stack_family", "web")
        is_web = ui_layer in ("html_css", "react") or stack_family == "web"

        if is_web:
            for f in final_files:
                fname = _Path(f.get("path", "")).name
                preview = f.get("content_preview", "")
                if not fname.endswith(".html") or not preview:
                    continue
                is_empty_shell = (
                    _re.search(r'<div\s+id=["\']app["\']>\s*<\/div>', preview, _re.IGNORECASE) or
                    _re.search(r'<body[^>]*>\s*<script', preview, _re.IGNORECASE) or
                    (_re.search(r'<(section|div|main)[^>]*>\s*<!--', preview, _re.IGNORECASE) and
                     len(_re.findall(r'<(input|button|select|table|form|ul|ol)', preview, _re.IGNORECASE)) == 0)
                )
                if is_empty_shell:
                    rule_issues.append(f"{fname}: HTML is an empty shell — no real DOM elements in preview")
                    rule_feedback.append(
                        f"{fname}: You generated an empty shell. Write ALL content directly in HTML — "
                        f"real <div class='card'>, <nav>, <button>, <input>, <table> elements. "
                        f"Do NOT render content exclusively from JavaScript."
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

        from backend.agents.architect import _extract_json_object
        data = _extract_json_object(response.content)
        if isinstance(data, dict):
            return ValidatorOutput(
                success=True,
                passed=data.get("passed", False),
                confidence=data.get("confidence", 0),
                issues=data.get("issues", []),
                fix_feedback=data.get("fix_feedback", ""),
            )
        else:
            logger.error("Validator JSON parse failed; raw head: %s", response.content[:120])
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

    def _check_final_files_complete(self, final_files: list[dict], requirement: str, contract: dict = None) -> dict:
        """Check if final files meet basic requirements — contract-driven, stack-agnostic."""
        contract = contract or {}
        ui_layer = contract.get("ui_layer", "")
        stack_family = contract.get("stack_family", "")

        def _as_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return list(v.values())
            return [v]

        entry_points = _as_list(contract.get("entry_points"))
        required_artifacts = _as_list(contract.get("required_artifacts"))
        missing = []

        # If Architect provided required_artifacts, use those as the authoritative check
        if required_artifacts:
            existing_names = {f["name"].lower() for f in final_files}
            existing_paths = {f.get("relative_path", "").lower() for f in final_files}
            for artifact in required_artifacts:
                if isinstance(artifact, dict):
                    path = artifact.get("path", "")
                elif isinstance(artifact, str):
                    path = artifact
                else:
                    path = ""
                if not path:
                    continue
                name = Path(path).name.lower()
                if name not in existing_names and path.lower() not in existing_paths:
                    missing.append(path)
            return {"ok": len(missing) == 0, "missing": missing}

        # If Architect provided entry_points, check those
        if entry_points:
            existing_names = {f["name"].lower() for f in final_files}
            for ep in entry_points:
                ep = ep if isinstance(ep, str) else (ep.get("path", "") if isinstance(ep, dict) else str(ep))
                if not ep:
                    continue
                name = Path(ep).name.lower()
                if name not in existing_names:
                    missing.append(ep)
            return {"ok": len(missing) == 0, "missing": missing}

        # Fallback: infer from stack_family / ui_layer
        is_web = ui_layer in ("html_css", "react") or stack_family == "web"
        is_python = stack_family == "python"
        is_node = stack_family == "node"

        file_names = {f["name"].lower() for f in final_files}

        if is_python:
            py_files = [f for f in final_files if f["name"].lower().endswith(".py")]
            if not py_files:
                missing.append("main.py or app.py")
        elif is_node:
            if "package.json" not in file_names:
                missing.append("package.json")
            js_files = [f for f in final_files if f["name"].lower().endswith((".js", ".ts"))]
            if not js_files:
                missing.append("index.js or server.js")
        elif is_web or not stack_family:
            # Default web check (backward compat)
            if not any(f["name"].lower().endswith(".html") for f in final_files):
                missing.append("index.html")
            if not any(f["name"].lower().endswith(".css") for f in final_files):
                missing.append("styles.css")
            if not any(f["name"].lower().endswith(".js") for f in final_files):
                missing.append("app.js")
        else:
            # "any" stack — just need at least one real file
            if not final_files:
                missing.append("source files")

        return {"ok": len(missing) == 0, "missing": missing}

    def _check_files_exist(self, generated_files: list[dict]) -> dict:
        missing = []
        for f in generated_files:
            path = Path(f.get("path", ""))
            if not path.exists():
                missing.append(f.get("relative_path", str(path)))
        return {"ok": len(missing) == 0, "missing": missing}
