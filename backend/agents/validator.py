import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

VALIDATOR_SYSTEM = """You are a code quality validator. Your ONLY job is to check if the build meets the original requirement and the architect's specification.

ROLE BOUNDARY (CRITICAL):
- You ONLY check functional completeness and spec compliance.
- You do NOT assess security risks — Hardener handles that.
- You do NOT evaluate code style, performance, or build success — SmokeTester handles that.
- You do NOT suggest new features or architectural changes.
- If the generated files list is empty or the requirement is missing, return {"passed": false, "confidence": 0, "issues": ["Missing inputs"], "fix_feedback": "Generate the required files."}.

ALWAYS respond with ONLY valid JSON. No explanations, no markdown, no code blocks:
{"passed": true|false, "confidence": 0-100, "issues": ["specific issues"], "fix_feedback": "actionable feedback"}"""


class ValidatorInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    generated_files: list[dict]
    findings: list[dict]
    build_dir: str


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

        # Build file summary with actual final files after FileConsolidation
        file_summary = []
        for f in final_files:
            entry = {
                "path": f.get("relative_path", str(f.get("path", ""))), 
                "size_bytes": f.get("size_bytes", f.get("size", 0))
            }
            preview = f.get("content_preview", "")
            if preview:
                entry["preview"] = preview[:200]
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
            ModelRequest(prompt=prompt, system_prompt=VALIDATOR_SYSTEM, temperature=0.2, max_tokens=1024)
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
                
                # Generate content preview for text files
                content_preview = ""
                try:
                    if file_path.suffix in ['.html', '.css', '.js', '.json', '.md', '.txt']:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content_preview = f.read(500)
                except Exception:
                    content_preview = ""
                
                final_files.append({
                    "path": str(file_path),
                    "relative_path": str(relative_path),
                    "name": file_path.name,
                    "size": size_bytes,
                    "size_bytes": size_bytes,
                    "content_preview": content_preview
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
