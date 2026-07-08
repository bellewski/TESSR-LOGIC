"""
Refiner agent — applies a user's conversational instruction to one generated file.
Powers the "Refine with AI" panel on the Build Detail page.
"""
import json
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


_TRIAGE_SYSTEM_DEFAULT = """You are the refinement assistant for a completed build. The user talks to you about changes they want.

Decide ONE of two actions:
- "edit": the user is asking for a change to the build. Choose which file(s) to modify (max 3, usually 1) and write a precise one-sentence edit instruction per file.
- "reply": the user is asking a question or discussing — no file change needed. Answer briefly and concretely, referring to the actual files.

Respond ONLY with valid JSON:
{"action": "edit"|"reply", "reply": "short answer or plan in plain language", "edits": [{"file": "name.ext", "instruction": "precise change to make in this file"}]}
For action "reply", edits must be []."""

_SUGGEST_SYSTEM_DEFAULT = """You are reviewing a completed build against its original requirement. Find the highest-impact concrete fixes.

Rules:
- Only suggest fixes you are confident about from the actual file contents (broken references, missing requirement features, dead links, placeholder text, wrong years, unstyled elements)
- Max 5 suggestions, most impactful first
- Each suggestion must be a single actionable edit to ONE file

Respond ONLY with valid JSON:
{"suggestions": [{"file": "name.ext", "issue": "what is wrong, one sentence", "fix": "imperative instruction to fix it, one sentence"}]}"""


def _collect_files(build_root: Path, per_file_cap: int = 1800) -> list[dict]:
    """Editable files with capped content for triage/suggest prompts."""
    src = build_root / "src"
    root = src if src.exists() else build_root
    out = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".html", ".css", ".js"):
            continue
        if "refine_history" in str(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append({"file": f.name, "size": len(text), "content": text[:per_file_cap]})
    return out[:12]


class RefineChat:
    """Conversational refinement: triage a user message into edits or a reply."""

    def __init__(self, provider: BaseModelProvider):
        self.provider = provider
        self.editor = RefinerAgent(provider)

    async def chat(self, *, build_root: Path, requirement: str, message: str,
                   history: list[dict] | None = None) -> dict:
        files = _collect_files(build_root)
        if not files:
            return {"reply": "No editable files (html/css/js) found in this build.", "edits": []}
        convo = ""
        for h in (history or [])[-8:]:
            who = "USER" if h.get("who") == "you" else "ASSISTANT"
            convo += f"{who}: {str(h.get('text', ''))[:400]}\n"
        prompt = (
            f"Original requirement:\n{requirement[:1500]}\n\n"
            f"Files in the build (name, size, content preview):\n{json.dumps(files, indent=1)[:9000]}\n\n"
            f"Conversation so far:\n{convo or '(none)'}\n"
            f"USER: {message}\n\n"
            'Decide the action and respond with only the JSON object.'
        )
        response = await self.provider.complete(
            ModelRequest(prompt=prompt,
                         system_prompt=load_system_prompt("refine_triage", _TRIAGE_SYSTEM_DEFAULT),
                         temperature=0.2, max_tokens=1024, response_format="json")
        )
        if not response.success:
            return {"reply": f"Model call failed: {response.error}", "edits": []}
        try:
            data = json.loads(response.content.strip())
        except json.JSONDecodeError:
            return {"reply": "I could not form a plan for that — try rephrasing.", "edits": []}

        results = []
        if data.get("action") == "edit":
            valid_names = {f["file"] for f in files}
            for e in (data.get("edits") or [])[:3]:
                fname, instr = str(e.get("file", "")), str(e.get("instruction", "")).strip()
                if fname not in valid_names or not instr:
                    results.append({"file": fname or "?", "success": False,
                                    "message": f"Skipped: '{fname}' is not an editable file in this build."})
                    continue
                r = await self.editor.refine(build_root=build_root, target_file=fname,
                                             instruction=instr, requirement=requirement)
                r["file"] = fname
                results.append(r)
        return {"reply": str(data.get("reply", "")).strip(), "edits": results}

    async def suggest(self, *, build_root: Path, requirement: str) -> dict:
        files = _collect_files(build_root, per_file_cap=2500)
        if not files:
            return {"suggestions": []}
        prompt = (
            f"Original requirement:\n{requirement[:1500]}\n\n"
            f"Files in the build:\n{json.dumps(files, indent=1)[:11000]}\n\n"
            "Review and respond with only the JSON object of suggestions."
        )
        response = await self.provider.complete(
            ModelRequest(prompt=prompt,
                         system_prompt=load_system_prompt("refine_suggest", _SUGGEST_SYSTEM_DEFAULT),
                         temperature=0.2, max_tokens=1536, response_format="json")
        )
        if not response.success:
            return {"suggestions": [], "error": response.error}
        try:
            data = json.loads(response.content.strip())
            sugg = [x for x in (data.get("suggestions") or [])
                    if isinstance(x, dict) and x.get("file") and x.get("fix")][:5]
            return {"suggestions": sugg}
        except json.JSONDecodeError:
            return {"suggestions": []}
