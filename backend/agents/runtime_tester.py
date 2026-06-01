"""
Runtime QA agent — executes generated web pages in a headless DOM (JSDOM via Node)
and catches RUNTIME failures that static checks miss: uncaught JS exceptions,
null-querySelector crashes, and pages that render almost nothing because their JS threw.

Findings are routed to the agent RESPONSIBLE for the failure (JS/logic -> coder),
so the orchestrator can hand a precise, surgical fix to one agent instead of
regenerating everything.
"""
import json
import logging
import subprocess
import shutil
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# repo_root/tools/runtime-check/check.js
_CHECKER = Path(__file__).resolve().parents[2] / "tools" / "runtime-check" / "check.js"


class RuntimeTesterInput(BaseModel):
    build_id: str
    build_dir: str
    contract: dict = {}


class RuntimeFinding(BaseModel):
    page: str
    category: str          # "js_runtime_error" | "empty_render"
    responsible_agent: str # which agent must fix it
    message: str


class RuntimeTesterOutput(BaseModel):
    success: bool
    skipped: bool = False
    error: str = ""
    findings: list[dict] = []
    # feedback bundled per responsible agent: { "coder": "...", "ui_designer": "..." }
    routed_feedback: dict = {}


def _route(category: str) -> str:
    """Map a runtime failure category to the agent responsible for fixing it."""
    return {
        "js_runtime_error": "coder",
        "empty_render": "coder",
        "functional_error": "coder",
    }.get(category, "coder")


class RuntimeTesterAgent:
    def __init__(self, build_dir: Path):
        self.build_dir = build_dir

    async def run(self, inp: RuntimeTesterInput) -> RuntimeTesterOutput:
        contract = inp.contract or {}
        ui_layer = contract.get("ui_layer", "html_css")
        stack_family = contract.get("stack_family", "web")
        is_web = ui_layer in ("html_css", "react") or stack_family == "web"
        if not is_web:
            return RuntimeTesterOutput(success=True, skipped=True)

        src = self.build_dir / "src"
        if not src.exists():
            return RuntimeTesterOutput(success=True, skipped=True)

        html_pages = sorted(p.name for p in src.glob("*.html"))
        if not html_pages:
            return RuntimeTesterOutput(success=True, skipped=True)

        node = shutil.which("node")
        if not node or not _CHECKER.exists():
            logger.warning("RuntimeTester: node or checker missing (node=%s, checker=%s) — skipping",
                           bool(node), _CHECKER.exists())
            return RuntimeTesterOutput(success=True, skipped=True)

        try:
            proc = subprocess.run(
                [node, str(_CHECKER), str(src), *html_pages],
                capture_output=True, text=True, timeout=120,
            )
        except Exception as e:
            logger.warning("RuntimeTester: checker failed to run: %s — skipping", e)
            return RuntimeTesterOutput(success=True, skipped=True)

        try:
            data = json.loads(proc.stdout.strip() or "{}")
        except Exception:
            logger.warning("RuntimeTester: unparseable checker output: %s", proc.stdout[:300])
            return RuntimeTesterOutput(success=True, skipped=True)

        findings: list[dict] = []
        for page in data.get("pages", []):
            errors = page.get("errors", [])
            func_errors = page.get("functionalErrors", [])
            pname = page.get("page", "?")
            # FUNCTIONAL failures: buttons/forms that throw or do nothing when used.
            if func_errors:
                findings.append(RuntimeFinding(
                    page=pname, category="functional_error",
                    responsible_agent=_route("functional_error"),
                    message="Interactions are broken:\n      " + "\n      ".join(func_errors[:6]),
                ).model_dump())
            if errors:
                msg = "; ".join(errors[:3])
                # Attach the PRECISE cause: which selectors matched nothing, and what
                # ids/classes actually exist — so the coder can fix the exact line.
                dead = page.get("deadSelectors", {}) or {}
                dead_ids = dead.get("getElementById", [])
                dead_q = dead.get("querySelector", [])
                detail = ""
                if dead_ids:
                    detail += f"\n    Dead getElementById (these IDs do not exist in the HTML): {dead_ids}"
                if dead_q:
                    detail += f"\n    Dead querySelector (these selectors match nothing): {dead_q}"
                if dead_ids or dead_q:
                    detail += f"\n    IDs that DO exist on the page: {page.get('availableIds', [])}"
                    detail += f"\n    Classes that DO exist on the page: {page.get('availableClasses', [])}"
                findings.append(RuntimeFinding(
                    page=pname, category="js_runtime_error",
                    responsible_agent=_route("js_runtime_error"),
                    message=msg + detail,
                ).model_dump())
            elif page.get("ok") and page.get("textLength", 0) < 40 and page.get("elementCount", 0) < 6:
                # Loaded clean but rendered almost nothing — likely JS that should
                # have populated content silently did nothing.
                findings.append(RuntimeFinding(
                    page=pname, category="empty_render",
                    responsible_agent=_route("empty_render"),
                    message=f"Page rendered almost no content (elements={page.get('elementCount')}, text={page.get('textLength')} chars).",
                ).model_dump())

        if not findings:
            return RuntimeTesterOutput(success=True, findings=[])

        # Bundle precise, surgical feedback per responsible agent.
        by_agent: dict[str, list[str]] = {}
        for f in findings:
            by_agent.setdefault(f["responsible_agent"], []).append(
                f"- {f['page']}: {f['message']}"
            )
        routed = {}
        for agent, lines in by_agent.items():
            routed[agent] = (
                "RUNTIME ERRORS detected by headless browser execution (these are real bugs that "
                "occur when the page loads in a browser):\n" + "\n".join(lines) + "\n\n"
                "Fix the SPECIFIC broken line(s) only. These are almost always a querySelector / "
                "getElementById that returned null because the selector does not match the actual "
                "HTML, or a handler attached before the element exists. "
                "Verify every selector matches an element that truly exists in the HTML, and guard "
                "against null where appropriate. Do NOT delete or rewrite working files — edit the "
                "broken lines in place until the page loads with zero JavaScript errors."
            )

        return RuntimeTesterOutput(success=False, findings=findings, routed_feedback=routed)
