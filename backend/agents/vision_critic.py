"""
Vision-grounded design critique — lets the pipeline actually SEE the rendered page.

JSDOM/static checks can't perceive layout. This renders the finished page in a real headless
browser (Playwright/Chromium), screenshots it, and asks a LOCAL vision model (via Ollama, e.g.
llava / qwen2.5-vl / bakllava) to critique the *rendered* result — catching "giant blob", empty
hero, cramped spacing, unstyled nav, etc. that text-only review misses.

FULLY OPTIONAL and graceful: if Playwright isn't installed, Chromium isn't installed, or no vision
model is available, it returns {available: False} and the pipeline behaves exactly as before. So it
can ship now and be "switched on" later by installing the deps. Stays offline (local browser +
local model, no network).

Enable on the box:
    pip install playwright && playwright install chromium
    ollama pull llava                 # or qwen2.5vl / bakllava; or set ollama_vision_model in settings
"""
import base64
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_VISION_HINTS = ("llava", "vision", "-vl", "qwen2.5vl", "qwen2-vl", "bakllava", "moondream", "minicpm-v")


def _live_settings() -> dict:
    try:
        from backend.database import SessionLocal
        from backend.repositories.settings_repo import SettingsRepository
        db = SessionLocal()
        try:
            return SettingsRepository(db).get_all() or {}
        finally:
            db.close()
    except Exception:
        return {}


def _base_url(live: dict) -> str:
    from backend.config import settings
    return (live.get("ollama_base_url") or settings.ollama_base_url).rstrip("/")


def _pick_vision_model(live: dict, base_url: str) -> str | None:
    # explicit setting wins
    m = live.get("ollama_vision_model")
    if m:
        return m
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        names = [x.get("name", "") for x in r.json().get("models", [])]
        for n in names:
            if any(h in n.lower() for h in _VISION_HINTS):
                return n
    except Exception:
        pass
    return None


async def _screenshot(html_path: Path, out_png: Path) -> bool:
    """Render the local HTML file to a PNG with Playwright. False if unavailable."""
    try:
        from playwright.async_api import async_playwright
    except Exception:
        logger.info("VisionCritic: playwright not installed — skipping render")
        return False
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox"])
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=15000)
            await page.screenshot(path=str(out_png), full_page=True)
            await browser.close()
        return out_png.exists()
    except Exception as e:
        logger.info("VisionCritic: render failed (%s) — skipping", e)
        return False


async def vision_review(build_dir: Path, contract: dict | None = None) -> dict:
    """Render + vision-critique the build's home page. Returns:
       {available, ok, score, issues:[...], feedback}  (available=False => no-op)."""
    contract = contract or {}
    ui_layer = contract.get("ui_layer", "html_css")
    if ui_layer not in ("html_css", "react") and contract.get("stack_family", "web") != "web":
        return {"available": False, "reason": "non-web"}

    src = build_dir / "src"
    if not src.exists():
        return {"available": False, "reason": "no src"}
    index = next((p for p in src.glob("*.html") if p.name.lower() in ("index.html", "home.html")), None)
    if not index:
        htmls = sorted(src.glob("*.html"))
        index = htmls[0] if htmls else None
    if not index:
        return {"available": False, "reason": "no html"}

    live = _live_settings()
    base_url = _base_url(live)
    model = _pick_vision_model(live, base_url)
    if not model:
        return {"available": False, "reason": "no vision model (pull llava / set ollama_vision_model)"}

    out_png = build_dir / "_vision.png"
    if not await _screenshot(index, out_png):
        return {"available": False, "reason": "render unavailable (pip install playwright && playwright install chromium)"}

    try:
        img_b64 = base64.b64encode(out_png.read_bytes()).decode()
    except Exception:
        return {"available": False, "reason": "screenshot unreadable"}

    prompt = (
        "You are a senior product designer reviewing a SCREENSHOT of a generated web page. Judge ONLY "
        "what you can SEE. Score 0-100 for professional visual quality and list concrete visible "
        "problems (e.g. a giant graphic filling the page, empty/blank hero, content glued to the edge, "
        "unstyled bulleted nav, cramped spacing, clashing colors, text overflow). "
        "Reply EXACTLY as: SCORE: <n>\\nISSUES:\\n- <issue>\\n- <issue>  (or 'ISSUES: none')."
    )
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{base_url}/api/generate", json={
                "model": model, "prompt": prompt, "images": [img_b64], "stream": False,
                "options": {"temperature": 0.2},
            })
            r.raise_for_status()
            text = r.json().get("response", "")
    except Exception as e:
        logger.info("VisionCritic: vision model call failed (%s)", e)
        return {"available": False, "reason": f"vision call failed: {e}"}

    # parse SCORE + ISSUES
    import re
    score = None
    msc = re.search(r"SCORE:\s*(\d{1,3})", text)
    if msc:
        score = max(0, min(100, int(msc.group(1))))
    issues = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("-") and len(line) > 2 and "none" not in line.lower():
            issues.append(line[1:].strip()[:200])
    feedback = ""
    if issues:
        feedback = ("VISION REVIEW (a vision model looked at the rendered page and saw): \n"
                    + "\n".join(f"- {i}" for i in issues[:8]))
    ok = (score is None or score >= 75) and not issues
    return {"available": True, "ok": ok, "score": score, "issues": issues, "feedback": feedback, "model": model}
