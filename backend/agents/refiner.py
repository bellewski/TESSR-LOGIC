"""
Refiner agent — applies a user's conversational instruction to one generated file.
Powers the "Refine with AI" panel on the Build Detail page.
"""
import logging
import re
import time
from pathlib import Path

from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

_REFINER_SYSTEM_DEFAULT = """You are a software engineer applying ONE user-requested change to ONE file.

Rules:
- Apply EXACTLY the requested change — nothing more
- Preserve all other content and functionality untouched
- Keep the file's existing style, palette, and structure

OUTPUT CONTRACT — CRITICAL:
- Your ENTIRE response is saved verbatim as the updated file
- Output ONLY the raw file contents — no markdown fences, no explanations, no markers
- The complete file, not a diff or fragment"""


class RefinerAgent:
    def __init__(self, provider: BaseModelProvider):
        self.provider = provider

    async def refine(self, *, build_root: Path, target_file: str, instruction: str,
                     requirement: str = "") -> dict:
        # Locate the file: prefer src/, fall back to newest match anywhere in the build
        name = Path(target_file).name
        candidates = [build_root / "src" / name]
        if not candidates[0].exists():
            found = sorted(build_root.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
            candidates = [f for f in found if "refine_history" not in str(f)]
        target = next((c for c in candidates if c.exists()), None)
        if not target:
            return {"success": False, "message": f"File '{name}' not found in this build."}

        original = target.read_text(encoding="utf-8", errors="replace")

        prompt = (
            f"Original project requirement (context only):\n{requirement[:1500]}\n\n"
            f"CURRENT CONTENT of {name}:\n{original}\n\n"
            f"USER'S REQUESTED CHANGE:\n{instruction}\n\n"
            f"Output the complete updated {name}."
        )
        response = await self.provider.complete(
            ModelRequest(
                prompt=prompt,
                system_prompt=load_system_prompt("refiner", _REFINER_SYSTEM_DEFAULT),
                temperature=0.15,
                max_tokens=8192,
            )
        )
        if not response.success:
            return {"success": False, "message": f"Model call failed: {response.error}"}

        body = response.content.strip()
        m = re.match(r"^```[a-zA-Z0-9_-]*\n(.*?)\n?```\s*$", body, re.DOTALL)
        if m:
            body = m.group(1).strip()
        body = re.sub(r"^\s*===FILE:[^\n]*===\s*\n", "", body)
        body = re.sub(r"\n?===END===\s*$", "", body).strip()

        # Plausibility: removals may legitimately shrink a file, but a collapse
        # to a fragment means the model failed the contract.
        removing = bool(re.search(r"\b(remove|delete|strip|drop|get rid of)\b", instruction.lower()))
        floor = 0.15 if removing else 0.4
        if len(body) < 20 or len(body) < len(original) * floor:
            return {"success": False,
                    "message": f"Refinement looked implausible ({len(body)} vs {len(original)} chars) — file left unchanged. Try rephrasing the instruction."}

        # Revision backup, then write
        history = build_root / "refine_history"
        history.mkdir(exist_ok=True)
        backup = history / f"{int(time.time())}_{name}"
        backup.write_text(original, encoding="utf-8")
        target.write_text(body, encoding="utf-8")
        logger.info("Refiner: updated %s (%d -> %d chars), backup at %s", name, len(original), len(body), backup.name)
        return {"success": True,
                "message": f"Updated {name} ({len(original)} -> {len(body)} chars). Previous version saved to refine_history/{backup.name}.",
                "file": name, "size": len(body)}
