import json
import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

RISKY_PATTERNS = [
    (r"\beval\s*\(", "high", "dangerous-eval", "Use of eval() detected — arbitrary code execution risk"),
    (r"subprocess.*shell\s*=\s*True", "high", "shell-injection", "subprocess with shell=True — shell injection risk"),
    (r"os\.system\s*\(", "medium", "os-exec", "os.system() call — prefer subprocess with list args"),
    (r'(?i)(password|secret|api_key|apikey|token)\s*=\s*["\'][^"\']{4,}["\']', "high", "hardcoded-secret", "Possible hardcoded secret or credential"),
    (r"CORS.*allow_origins.*\*", "medium", "permissive-cors", "Wildcard CORS origin detected"),
    (r"DEBUG\s*=\s*True", "low", "debug-mode", "DEBUG=True should not be used in production"),
    (r"0\.0\.0\.0", "low", "bind-all", "Binding to 0.0.0.0 exposes service on all interfaces"),
    (r"pickle\.loads?\s*\(", "high", "pickle-deserialization", "pickle.load() — unsafe deserialization"),
    (r"__import__\s*\(", "medium", "dynamic-import", "Dynamic __import__() usage detected"),
    (r"exec\s*\(", "high", "exec-call", "exec() call — arbitrary code execution risk"),
]

HARDENER_SYSTEM = """You are a security-focused code reviewer. Your ONLY job is to assess security risks in code.

ROLE BOUNDARY (CRITICAL):
- You ONLY assess security risks: eval, subprocess with shell=True, hardcoded secrets, wildcard CORS, unsafe deserialization, exec, etc.
- You do NOT evaluate code quality, functional correctness, spec compliance, style, or completeness.
- You do NOT suggest features, refactors, or performance improvements.
- You do NOT write code — only produce remediation notes.

Output ONLY a JSON array of remediation objects:
[{"finding_id": "0", "suggestion": "specific fix advice"}]
Return only the JSON array."""


class HardenerInput(BaseModel):
    build_id: str
    mode: str
    generated_files: list[dict]
    build_dir: str


class HardenerOutput(BaseModel):
    success: bool
    error: str = ""
    findings: list[dict] = []
    findings_path: str = ""
    remediation_path: str = ""


class HardenerAgent(BaseAgent[HardenerInput, HardenerOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: HardenerInput) -> HardenerOutput:
        findings = []
        src_dir = Path(input_data.build_dir) / "src"

        for file_info in input_data.generated_files:
            fpath = Path(file_info.get("path", ""))
            if not fpath.exists():
                continue
            if fpath.suffix not in (".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".env"):
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for line_no, line in enumerate(text.splitlines(), start=1):
                for pattern, severity, category, desc in RISKY_PATTERNS:
                    if re.search(pattern, line):
                        findings.append({
                            "id": str(len(findings)),
                            "severity": severity,
                            "category": category,
                            "file_path": file_info.get("relative_path", str(fpath)),
                            "line_number": line_no,
                            "description": desc,
                            "line_content": line.strip()[:200],
                        })

        remediations = []
        if findings:
            findings_summary = json.dumps([{k: v for k, v in f.items() if k != "line_content"} for f in findings], indent=2)
            response = await self.provider.complete(
                ModelRequest(
                    prompt=f"Findings:\n{findings_summary}\n\nProvide remediation suggestions.",
                    system_prompt=HARDENER_SYSTEM,
                    temperature=0.2,
                    max_tokens=1024,
                )
            )
            if response.success:
                try:
                    content = response.content.strip()
                    if content.startswith("```"):
                        lines = content.split("\n")
                        content = "\n".join(lines[1:-1])
                    remediations = json.loads(content)
                except Exception as e:
                    logger.warning("Hardener remediation parse failed: %s", e)
                    remediations = [{"finding_id": f["id"], "suggestion": "Review and address manually"} for f in findings]

        for finding in findings:
            matching = [r for r in remediations if r.get("finding_id") == finding["id"]]
            finding["remediation"] = matching[0]["suggestion"] if matching else "Review and address manually"

        findings_path = self.build_dir / "findings.json"
        findings_path.write_text(json.dumps(findings, indent=2), encoding="utf-8")

        remediation_path = self.build_dir / "remediation_notes.md"
        md = "# Remediation Notes\n\n"
        if findings:
            for f in findings:
                md += f"## [{f['severity'].upper()}] {f['category']}\n"
                md += f"**File**: `{f['file_path']}` line {f.get('line_number', '?')}\n\n"
                md += f"**Issue**: {f['description']}\n\n"
                md += f"**Fix**: {f.get('remediation', 'Review manually')}\n\n---\n\n"
        else:
            md += "No findings detected by heuristic scan.\n"
        remediation_path.write_text(md, encoding="utf-8")

        return HardenerOutput(
            success=True,
            findings=findings,
            findings_path=str(findings_path),
            remediation_path=str(remediation_path),
        )
