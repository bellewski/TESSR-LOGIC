"""
Fixer agent that applies security and quality findings from Hardener and Validator.
Actually implements the fixes instead of just reporting them.
"""

import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_FIXER_SYSTEM_DEFAULT = """You are a code fixer. Your ONLY job is to apply security and quality fixes found by other agents.

ROLE BOUNDARY (CRITICAL):
- You ONLY apply fixes to existing files based on findings provided
- You do NOT add new features, change architecture, or refactor beyond the fixes
- You do NOT assess security risks - Hardener already found them
- You do NOT validate functionality - Validator already did that
- You ONLY implement the specific remediation steps for each finding

FIXING RULES:
1. Apply ONLY the fixes listed in the findings
2. Preserve existing functionality while fixing issues
3. Use the exact remediation steps provided in each finding
4. For HIGH severity findings, be extra careful and conservative
5. If a fix is unclear, make the minimal safe change
6. Never break existing functionality while applying fixes

OUTPUT FORMAT - ONLY file blocks in this exact format:
===FILE: relative/path.ext===
<fixed code here>
===END===

CRITICAL: Every file must be complete working code after fixes. NO partial files, NO stubs."""

class FixerInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    generated_files: list[dict]
    findings: list[dict]
    build_dir: str

class FixerOutput(BaseModel):
    success: bool
    error: str = ""
    fixed_files: list[dict] = []
    applied_fixes: list[str] = []

class FixerAgent(BaseAgent[FixerInput, FixerOutput]):
    """Applies security and quality fixes found by other agents."""
    
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: FixerInput) -> FixerOutput:
        """Apply fixes based on findings from Hardener and Validator."""
        
        # Filter for fixable findings (exclude informational findings)
        fixable_findings = [
            f for f in input_data.findings 
            if f.get("severity") in ["high", "medium", "low"] and f.get("remediation")
        ]
        
        if not fixable_findings:
            return FixerOutput(
                success=True,
                applied_fixes=["No fixes needed - no actionable findings"]
            )
        
        # Group findings by file for efficient fixing
        findings_by_file = {}
        for finding in fixable_findings:
            file_path = finding.get("file_path", "")
            if file_path:
                if file_path not in findings_by_file:
                    findings_by_file[file_path] = []
                findings_by_file[file_path].append(finding)
        
        # Generate prompt for each file that needs fixing
        all_fixed_files = []
        all_applied_fixes = []
        
        for file_path, file_findings in findings_by_file.items():
            # Read current file content
            full_path = self.build_dir / "src" / file_path
            if not full_path.exists():
                full_path = self.build_dir / file_path
            
            if not full_path.exists():
                continue
                
            current_content = full_path.read_text(encoding="utf-8")
            
            # Create fixing prompt
            findings_text = "\n".join([
                f"- {f.get('severity', 'unknown').upper()}: {f.get('description', '')}\n"
                f"  Line {f.get('line_number', 'unknown')}: {f.get('remediation', '')}"
                for f in file_findings
            ])
            
            prompt = (
                f"Project: {input_data.project_name}\n"
                f"File to fix: {file_path}\n\n"
                f"CURRENT CONTENT:\n{current_content}\n\n"
                f"FINDINGS TO FIX:\n{findings_text}\n\n"
                f"Apply the remediation steps to fix the findings. "
                f"Preserve all existing functionality. "
                f"Output the complete fixed file."
            )
            
            try:
                response = await self.provider.complete(
                    ModelRequest(
                        prompt=prompt,
                        system_prompt=load_system_prompt("fixer", _FIXER_SYSTEM_DEFAULT),
                        temperature=0.1,  # Low temperature for conservative fixes
                        max_tokens=4096,
                    )
                )
                
                if not response.success:
                    logger.error(f"Fixer failed for {file_path}: {response.error}")
                    continue

                # Parse all fixed files from response (may fix multiple at once)
                fixed_file_dicts = self._parse_all_fixed_files(response.content, self.build_dir)

                if fixed_file_dicts:
                    for fixed in fixed_file_dicts:
                        # Resolve path relative to build_dir/src or build_dir
                        rel = fixed["path"].lstrip("/\\")
                        target = self.build_dir / "src" / rel
                        if not target.exists():
                            target = self.build_dir / rel
                        if target.exists():
                            target.write_text(fixed["content"], encoding="utf-8")
                            all_fixed_files.append({
                                "path": str(target),
                                "relative_path": rel,
                                "size": len(fixed["content"]),
                                "content_preview": fixed["content"][:200],
                            })
                else:
                    # Fallback: single-file extraction
                    fixed_content = self._extract_fixed_content(response.content)
                    if fixed_content:
                        full_path.write_text(fixed_content, encoding="utf-8")
                        all_fixed_files.append({
                            "path": str(full_path),
                            "relative_path": file_path,
                            "size": len(fixed_content),
                            "content_preview": fixed_content[:200],
                        })

                all_applied_fixes.extend([
                    f"Fixed {file_path}: {f.get('description', '')}"
                    for f in file_findings
                ])
                    
            except Exception as e:
                logger.error(f"Error fixing {file_path}: {e}")
                continue
        
        return FixerOutput(
            success=True,
            fixed_files=all_fixed_files,
            applied_fixes=all_applied_fixes
        )
    
    def _parse_all_fixed_files(self, response_content: str, build_dir: Path) -> list[dict]:
        """Parse all fixed files from the LLM response using the same pattern as CoderAgent."""
        import re
        results = []
        parts = re.split(r'===FILE:\s*', response_content)
        for part in parts[1:]:
            header, _, body = part.partition('\n')
            path = header.replace('===', '').strip()
            body = re.split(r'===END===|===FILE:', body)[0]
            # Strip markdown code fences
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            body = body.strip('\n')
            if not path or not body:
                continue
            results.append({"path": path, "content": body})
        return results

    def _extract_fixed_content(self, response_content: str) -> str:
        """Extract the first fixed file content from the LLM response (single-file fallback)."""
        import re
        parts = re.split(r'===FILE:\s*', response_content)
        if len(parts) < 2:
            return ""
        _, _, body = parts[1].partition('\n')
        body = re.split(r'===END===|===FILE:', body)[0]
        body = re.sub(r'^```\w*\n', '', body)
        body = re.sub(r'\n```\s*$', '', body)
        return body.strip('\n')
