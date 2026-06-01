"""
Design Critic — the visual-quality gate for web builds.

Runtime QA proves a page *works* (no JS errors, interactions fire). It says nothing
about whether the page *looks professional*. The Design Critic fills that gap: it
inspects the final HTML + CSS and judges it against modern, general design PRINCIPLES
(centered max-width container, real type/spacing scale, card surfaces with elevation,
a responsive grid, inline SVG icons instead of emoji/unicode, a hero that doesn't
overflow). When it falls short it routes a SURGICAL, additive critique to the agent
responsible: CSS/visual issues → ui_designer, markup/structure issues → coder.

It is LLM-driven against principles (NOT hardcoded templates), so it never dictates a
specific design — it only enforces a professional baseline, same way a senior designer
would in review. Cheap, deterministic heuristics run first to ground the model and to
keep the gate working even if the LLM returns noise.
"""
import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel

from backend.providers.base import BaseModelProvider, ModelRequest
from backend.agents.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

# A working but visually-weak page should not block delivery forever. The pipeline caps
# how many design-fix rounds it spends; this is the score (0-100) at/above which we
# consider the page professional enough to ship.
PASS_SCORE = 78

_SYSTEM = """You are a senior product designer reviewing a generated website for PROFESSIONAL visual quality.
You are NOT checking whether it works (another stage does that). You judge ONLY how it LOOKS, against
modern SaaS design standards (think Linear, Vercel, Stripe).

Score the page 0-100 on these professional baselines, and list concrete, specific problems:
- LAYOUT: content sits in a CENTERED max-width container with generous padding (NOT glued to the page edges); sections have vertical rhythm/spacing.
- HIERARCHY: a clear type scale; the hero headline is large (clamp) but does NOT overflow its container.
- SURFACES: feature/step content sits on elevated CARDS (background lighter/darker than the page, rounded corners, soft shadow) — not flat stacked text.
- GRID: groups of items (features, steps) use a responsive grid, not a single left-aligned column.
- ICONS: icons are inline <svg> — NOT emoji or unicode characters (🤖 ⚡ 🔒 are amateur tells).
- POLISH: consistent spacing scale, hover/transition states, cohesive color system.

You will be given the page's structural facts (from automated inspection) plus the HTML and CSS.
Trust the structural facts. Be strict — a page that works but looks like a 2005 template should score LOW.

Return ONLY this JSON (no prose, no markdown):
{
  "score": <0-100 integer>,
  "summary": "<one sentence overall verdict>",
  "ui_designer_fixes": ["<specific CSS/visual fix>", ...],
  "coder_fixes": ["<specific HTML/markup/structure fix, e.g. wrap content in a .container, replace emoji with inline svg>", ...]
}
Put CSS/styling problems in ui_designer_fixes and HTML/markup/structure problems in coder_fixes. Either list may be empty."""

# Emoji / pictographic ranges — their presence as "icons" is a strong amateur signal.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]"
)


class DesignCriticInput(BaseModel):
    build_id: str
    build_dir: str
    contract: dict = {}


class DesignCriticOutput(BaseModel):
    success: bool                 # True = professional enough to ship
    skipped: bool = False
    error: str = ""
    score: int = 0
    issues: list[str] = []
    # surgical critique bundled per responsible agent: {"ui_designer": "...", "coder": "..."}
    routed_feedback: dict = {}


def _heuristics(html_all: str, css_all: str) -> tuple[list[str], list[str], int]:
    """Cheap, deterministic structural facts. Returns (coder_issues, ui_issues, penalty)."""
    coder_issues: list[str] = []
    ui_issues: list[str] = []
    penalty = 0
    html_l = html_all.lower()
    css_l = css_all.lower()

    # Emoji used where icons belong → markup problem (coder should emit inline SVG).
    emojis = sorted(set(_EMOJI_RE.findall(html_all)))
    if emojis:
        coder_issues.append(
            f"Replace emoji/unicode icons ({' '.join(emojis[:8])}) with inline <svg> icons — "
            f"emoji as icons looks amateur and renders inconsistently."
        )
        penalty += 18

    # No centered container → content hugs the edge (the single most common amateur tell).
    has_container = bool(re.search(r"max-width\s*:\s*\d", css_l)) and (
        "margin: 0 auto" in css_l or "margin:0 auto" in css_l or "margin-inline: auto" in css_l
    )
    if not has_container:
        ui_issues.append(
            "Add a centered content container: a wrapper with max-width (~1100-1280px), "
            "margin-inline:auto, and horizontal padding so content is not glued to the screen edges."
        )
        penalty += 16

    # No grid for repeated blocks → single left column.
    if "grid-template-columns" not in css_l and "display:grid" not in css_l and "display: grid" not in css_l:
        ui_issues.append(
            "Use a responsive grid (display:grid; grid-template-columns: repeat(auto-fit, minmax(...))) "
            "for feature/step groups instead of a single stacked column."
        )
        penalty += 12

    # No elevated card surfaces → flat page.
    has_shadow = "box-shadow" in css_l
    has_radius = "border-radius" in css_l
    if not (has_shadow and has_radius):
        ui_issues.append(
            "Give feature/step content elevated card surfaces: a panel background distinct from the page, "
            "border-radius, soft box-shadow, and padding."
        )
        penalty += 12

    # No hover/transition polish.
    if ":hover" not in css_l and "transition" not in css_l:
        ui_issues.append("Add hover states and transitions for interactive polish.")
        penalty += 6

    # UNSIZED SVG → the "giant black blob" bug. Inline <svg> with a viewBox but no width/height
    # attribute, AND no CSS svg sizing, expands to fill its container. This is catastrophic
    # visually, so penalize hard.
    svg_tags = re.findall(r"<svg\b[^>]*>", html_all, re.IGNORECASE)
    unsized = [t for t in svg_tags if "viewbox" in t.lower()
               and not re.search(r'\b(width|height)\s*=', t, re.IGNORECASE)
               and "style=" not in t.lower()]
    css_sizes_svg = bool(re.search(r"\bsvg\b[^{]*\{[^}]*(max-width|width|height)", css_l)) \
        or "svg{" in css_l.replace(" ", "")
    if unsized and not css_sizes_svg:
        ui_issues.append(
            "Inline <svg> elements have a viewBox but no width/height and the CSS does not size svg — "
            "they will expand to fill the page (giant black blob). Add `svg{max-width:100%;height:auto}`, "
            "give icon svgs fixed ~24px sizes by class, constrain hero/illustration svgs (max-height), "
            "and set an explicit fill color."
        )
        penalty += 22

    # Hero overflow guard — big font without wrapping safety.
    if "clamp(" in css_l and ("overflow-wrap" not in css_l and "word-wrap" not in css_l and "max-width" not in css_l):
        ui_issues.append(
            "The oversized hero heading can overflow — constrain it (max-width / overflow-wrap:break-word) "
            "so large text wraps instead of running off the edge."
        )
        penalty += 6

    return coder_issues, ui_issues, penalty


class DesignCriticAgent:
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, inp: DesignCriticInput) -> DesignCriticOutput:
        contract = inp.contract or {}
        ui_layer = contract.get("ui_layer", "html_css")
        stack_family = contract.get("stack_family", "web")
        if ui_layer not in ("html_css", "react") and stack_family != "web":
            return DesignCriticOutput(success=True, skipped=True)

        src = self.build_dir / "src"
        if not src.exists():
            return DesignCriticOutput(success=True, skipped=True)

        html_files = sorted(src.glob("*.html"))
        css_files = sorted(src.rglob("*.css"))
        if not html_files:
            return DesignCriticOutput(success=True, skipped=True)

        def _read(paths, cap):
            out, used = [], 0
            for p in paths:
                try:
                    t = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                blk = f"/* {p.name} */\n{t}\n"
                if used + len(blk) <= cap:
                    out.append(blk); used += len(blk)
            return "".join(out)

        # Use the home/index page (or the first) as the representative sample, plus all CSS.
        index = next((p for p in html_files if p.name.lower() in ("index.html", "home.html")), html_files[0])
        html_all = _read([index], 14000)
        html_for_emoji = "".join(p.read_text(encoding="utf-8", errors="replace") for p in html_files
                                 if p.stat().st_size < 200_000)
        css_all = _read(css_files, 22000)

        coder_h, ui_h, penalty = _heuristics(html_for_emoji, css_all)

        facts = (
            "AUTOMATED STRUCTURAL INSPECTION (trust these):\n"
            f"- HTML pages: {[p.name for p in html_files]}\n"
            f"- CSS files: {[p.name for p in css_files]}\n"
            f"- Centered max-width container detected: {'no' if any('container' in i for i in ui_h) else 'yes'}\n"
            f"- Responsive grid detected: {'no' if any('grid' in i for i in ui_h) else 'yes'}\n"
            f"- Elevated card surfaces detected: {'no' if any('card' in i for i in ui_h) else 'yes'}\n"
            f"- Emoji used as icons: {'yes' if coder_h else 'no'}\n"
        )
        prompt = (
            f"{facts}\n"
            f"HOME PAGE HTML:\n{html_all}\n\n"
            f"STYLESHEET(S):\n{css_all}\n\n"
            "Review the visual quality and return ONLY the JSON object specified."
        )

        llm_score = None
        llm_summary = ""
        ui_fixes: list[str] = []
        coder_fixes: list[str] = []
        try:
            resp = await self.provider.complete(ModelRequest(
                prompt=prompt, system_prompt=load_system_prompt("design_critic", _SYSTEM),
                temperature=0.2, max_tokens=900, num_ctx=16384,
            ))
            if resp.success and resp.content:
                m = re.search(r"\{.*\}", resp.content, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                    llm_score = int(data.get("score", 0))
                    llm_summary = str(data.get("summary", ""))[:200]
                    ui_fixes = [str(x) for x in (data.get("ui_designer_fixes") or [])][:8]
                    coder_fixes = [str(x) for x in (data.get("coder_fixes") or [])][:8]
        except Exception as e:
            logger.warning("DesignCritic LLM judge failed (%s) — falling back to heuristics", e)

        # Merge LLM + heuristic findings (dedup-ish), and combine scores conservatively:
        # take the LOWER of the LLM score and a heuristic-derived score, so a structural
        # red flag the model glossed over still drags the verdict down.
        heuristic_score = max(0, 100 - penalty)
        if llm_score is None:
            score = heuristic_score
            llm_summary = llm_summary or "Heuristic-only review (LLM unavailable)."
        else:
            score = min(llm_score, heuristic_score)

        ui_all = ui_h + [f for f in ui_fixes if f not in ui_h]
        coder_all = coder_h + [f for f in coder_fixes if f not in coder_h]
        issues = [f"[CSS] {x}" for x in ui_all] + [f"[HTML] {x}" for x in coder_all]

        if score >= PASS_SCORE:
            return DesignCriticOutput(success=True, score=score, issues=issues)

        routed = {}
        if ui_all:
            routed["ui_designer"] = (
                "DESIGN REVIEW — the stylesheet must look like a modern, professional SaaS site. "
                f"Reviewer score: {score}/100. {llm_summary}\n"
                "Fix these specific visual problems by EDITING the existing CSS (keep the file, do not start over):\n"
                + "\n".join(f"- {x}" for x in ui_all) +
                "\nKeep it fully self-contained (no external assets). Do not change page text or break layout selectors."
            )
        if coder_all:
            routed["coder"] = (
                "DESIGN REVIEW — markup/structure changes needed for a professional look "
                f"(reviewer score {score}/100). Edit the existing HTML in place (keep all files):\n"
                + "\n".join(f"- {x}" for x in coder_all) +
                "\nWrap page content in a centered container element the CSS can target, and use inline "
                "<svg> for icons instead of emoji. Do not remove existing content or break element ids/classes."
            )

        return DesignCriticOutput(success=False, score=score, issues=issues, routed_feedback=routed)
