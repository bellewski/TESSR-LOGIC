import re
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.orchestrator.event_bus import event_bus

logger = logging.getLogger(__name__)

_CODER_SYSTEM_DEFAULT = """You are an expert software engineer. Your ONLY job is to generate PROFESSIONAL, PRODUCTION-READY source code files from the provided file_plan and requirement. 

QUALITY STANDARDS (non-negotiable):
1. Every file MUST be complete, working, production-quality code. NO stubs, NO TODOs, NO placeholder comments.
2. Your code MUST perfectly match the requested tech stack and framework.
3. Data MUST be realistic: real names, real descriptions, real numbers — NOT "Lorem ipsum" or "Placeholder".

ROLE BOUNDARY (CRITICAL):
- You ONLY write code files matching the file_plan.
- You do NOT modify the specification, add files not in the plan, or remove files from the plan.
- You do NOT assess security, evaluate quality, or judge completeness — other agents handle that.

CRITICAL RULES — VIOLATING ANY OF THESE IS A FAILURE:
1. Your ENTIRE response MUST consist ONLY of file blocks in this exact format. NOTHING ELSE:
   ===FILE: relative/path/to/file.ext===
   <code here>
   ===END===

2. If you previously received FIX FEEDBACK, you MUST address every issue listed. Rewrite affected files completely.

DONE_WHEN:
- Your response contains ONLY ===FILE: ... ===END=== blocks.
- Every file in the current batch has been generated.
- Every file contains actual working code, not stubs or comments.
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

        await event_bus.publish(input_data.build_id, {
            "event_type": "agent_typing",
            "phase": "coding",
            "payload": f">>> HANDOFF RECEIVED: Architect -> Coder\n"
                       f">>> TASK: Generate {len(file_plan)} planned files.\n\n"
        })

        if input_data.fix_feedback:
            await event_bus.publish(input_data.build_id, {
                "event_type": "agent_typing",
                "phase": "coding",
                "payload": f">>> ⚠️ REVISION REQUESTED: Fixing errors from previous run...\n\n"
            })

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
                stack_warning = "\n\n!!! CRITICAL: STACK IS HTML5/VANILLA - NO FRAMEWORKS ALLOWED !!!\nNEVER use React, JSX, Vue, Angular, or any build tools. ONLY plain HTML, CSS, and vanilla JavaScript. Include <link rel='stylesheet' href='styles.css'> and semantic HTML.\n"
            
            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target.upper()}{stack_warning}\n"
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

            # Show file creation messages
            file_names = ", ".join([f.get('path', 'unknown') for f in batch])
            await event_bus.publish(input_data.build_id, {
                "event_type": "agent_typing",
                "phase": "coding",
                "payload": f"\n=========================================\n"
                           f"✍️ NOW WRITING: {file_names}\n"
                           f"=========================================\n\n"
            })

            # Generate code with streaming
            full_content = ""
            try:
                req = ModelRequest(
                    prompt=prompt,
                    system_prompt=load_system_prompt("coder", _CODER_SYSTEM_DEFAULT),
                    temperature=0.2,
                    max_tokens=8192,
                )
                async for chunk in self.provider.stream_complete(req):
                    full_content += chunk
                    await event_bus.publish(input_data.build_id, {
                        "event_type": "agent_typing",
                        "phase": "coding",
                        "payload": chunk
                    })
                
                await event_bus.publish(input_data.build_id, {
                    "event_type": "agent_typing",
                    "phase": "coding",
                    "payload": f"\n\n>>> ✅ Finished batch {batch_idx + 1}/{len(batches)}\n"
                })
            except Exception as e:
                return CoderOutput(success=False, error=str(e))

            generated = self._parse_files(full_content)
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

        # Self-validation 2: FAIL if file_plan coverage is incomplete
        planned_paths = {self._sanitize_path(f.get("path", "")) for f in input_data.file_plan if f.get("path")}
        generated_paths = {self._sanitize_path(f.get("relative_path", "").replace("src/", "")) for f in all_generated}
        # Only check planned paths that look like source files (not docs)
        source_plan = {p for p in planned_paths if p and not p.endswith((".md", ".txt", ".rst"))}
        if source_plan:
            missing = source_plan - generated_paths
            if missing:
                logger.error("Coder missing %d planned files: %s", len(missing), missing)
                return CoderOutput(success=False, error=f"File plan contract violation: missing planned files {missing}")

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
