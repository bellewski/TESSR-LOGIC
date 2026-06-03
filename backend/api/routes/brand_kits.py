"""Brand kits API — list/inspect offline brand fixtures and serve their logos."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.core import brand_kits

router = APIRouter(prefix="/brand-kits", tags=["brand-kits"])


@router.get("")
def list_brand_kits():
    return {"brand_kits": brand_kits.list_kits()}


@router.get("/{slug}")
def get_brand_kit(slug: str):
    kit = brand_kits.get_kit(slug)
    if not kit:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return kit


@router.get("/{slug}/logo.svg")
def get_brand_logo(slug: str):
    p = brand_kits.kit_dir(slug) / "logo.svg"
    if not p.exists():
        # fall back to the wordmark used by tessr-logic
        p = brand_kits.kit_dir(slug) / "logo" / "tessr-logo.svg"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(str(p), media_type="image/svg+xml")
