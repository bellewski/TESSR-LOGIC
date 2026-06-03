"""
Brand kits — offline design fixtures under assets/brand-kits/<slug>/brand.json.

Lets a build be tagged with a brand so the Architect/Coder/UI-Designer produce on-brand
output without the user re-describing colors/fonts every time. Fully offline: the kit is
read from disk and its tokens are appended to the build requirement as a BRAND KIT block.
"""
import json
import re
import logging
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)

_KITS_DIR = Path(settings.workspace_path).resolve().parent.parent / "assets" / "brand-kits"
_SLUG = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _SLUG.sub("-", (s or "").lower()).strip("-") or "brand"


def list_kits() -> list[dict]:
    out = []
    if not _KITS_DIR.exists():
        return out
    for d in sorted(_KITS_DIR.glob("*/brand.json")):
        try:
            b = json.loads(d.read_text(encoding="utf-8"))
        except Exception:
            continue
        colors = b.get("colors", {})
        out.append({
            "slug": d.parent.name,
            "name": b.get("name", d.parent.name),
            "industry": b.get("industry", ""),
            "tagline": b.get("tagline", ""),
            "primary": colors.get("primary", ""),
            "accent": colors.get("accent", ""),
            "bg": colors.get("bg", ""),
            "has_logo": (d.parent / "logo.svg").exists(),
        })
    return out


def get_kit(slug: str) -> dict | None:
    f = _KITS_DIR / slug / "brand.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def kit_dir(slug: str) -> Path:
    return _KITS_DIR / slug


def save_kit(data: dict, logo_svg: str | None = None) -> dict:
    """Create/overwrite a brand kit folder (brand.json + optional logo.svg). Returns summary."""
    slug = _slugify(data.get("slug") or data.get("name") or "brand")
    c = data.get("colors") or {}
    primary = c.get("primary") or "#6366f1"
    accent = c.get("accent") or "#8b5cf6"
    # Fill sensible defaults so requirement_block always has a full token set.
    colors = {
        "bg": c.get("bg") or "#0b0e1a",
        "bg_elevated": c.get("bg_elevated") or "#141a2e",
        "surface": c.get("surface") or "#1b2238",
        "border": c.get("border") or "#2a3350",
        "primary": primary,
        "primary_hover": c.get("primary_hover") or primary,
        "accent": accent,
        "text": c.get("text") or "#e5e7eb",
        "muted": c.get("muted") or "#9ca3af",
        "gradient_hero": c.get("gradient_hero") or f"linear-gradient(135deg,{primary} 0%,{accent} 100%)",
    }
    rec = {
        "name": str(data.get("name", "") or slug)[:120],
        "slug": slug,
        "industry": str(data.get("industry", ""))[:120],
        "tagline": str(data.get("tagline", ""))[:200],
        "voice": {
            "tone": str((data.get("voice") or {}).get("tone", ""))[:160],
            "audience": str((data.get("voice") or {}).get("audience", ""))[:160],
        },
        "colors": colors,
        "typography": {
            "font_stack": str(data.get("font_stack", "") or "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"),
            "scale": {"display": "clamp(2.5rem,6vw,4.5rem)", "h1": "2.25rem", "h2": "1.5rem", "body": "1rem"},
            "line_height": 1.6,
        },
        "aesthetic": [str(x).strip() for x in (data.get("aesthetic") or []) if str(x).strip()][:12],
        "constraints": {"offline": True, "no_external_assets": True, "icons": "inline SVG only",
                        "svg_sizing": "svg{max-width:100%;height:auto}; icons ~24px; illustrations constrained"},
    }
    d = _KITS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "brand.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    if logo_svg and "<svg" in logo_svg.lower():
        (d / "logo.svg").write_text(logo_svg.strip(), encoding="utf-8")
    return {"slug": slug, "name": rec["name"], "has_logo": (d / "logo.svg").exists()}


def delete_kit(slug: str) -> bool:
    import shutil
    d = _KITS_DIR / _slugify(slug)
    if not (d / "brand.json").exists():
        return False
    shutil.rmtree(d)
    return True


def requirement_block(slug: str) -> str:
    """Render a brand kit as a precise design directive to append to a build requirement."""
    b = get_kit(slug)
    if not b:
        return ""
    c = b.get("colors", {})
    t = b.get("typography", {})
    scale = t.get("scale", {})
    lines = [
        "\n\n=== BRAND KIT (apply this exact identity) ===",
        f"Brand: {b.get('name','')} — {b.get('industry','')}",
    ]
    if b.get("tagline"):
        lines.append(f"Tagline: {b['tagline']}")
    voice = b.get("voice", {})
    if voice:
        lines.append(f"Voice: {voice.get('tone','')} (audience: {voice.get('audience','')})")
    if c:
        lines.append(
            "Colors — bg {bg}, elevated {be}, surface {su}, border {bo}, primary {pr}, "
            "accent {ac}, text {tx}, muted {mu}.".format(
                bg=c.get("bg",""), be=c.get("bg_elevated",""), su=c.get("surface",""),
                bo=c.get("border",""), pr=c.get("primary",""), ac=c.get("accent",""),
                tx=c.get("text",""), mu=c.get("muted",""))
        )
        if c.get("gradient_hero"):
            lines.append(f"Hero gradient: {c['gradient_hero']}")
    if t.get("font_stack"):
        lines.append(f"Font: {t['font_stack']}; display {scale.get('display','')}, h1 {scale.get('h1','')}, body {scale.get('body','')}.")
    if b.get("aesthetic"):
        lines.append("Aesthetic: " + ", ".join(b["aesthetic"]) + ".")
    lines.append(
        "Use these EXACT colors/fonts as CSS :root variables. Inline SVG icons only (never emoji). "
        "Every svg must be sized (svg{max-width:100%;height:auto}; icons ~24px). Fully self-contained, no external assets."
    )
    if (kit_dir(slug) / "logo.svg").exists():
        lines.append("A logo.svg for this brand is available in the brand kit; create a matching inline-SVG logo in the header.")
    return "\n".join(lines)
