"""Brand kits API — list/inspect/create offline brand fixtures and serve their logos."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core import brand_kits

router = APIRouter(prefix="/brand-kits", tags=["brand-kits"])


class Voice(BaseModel):
    tone: str = ""
    audience: str = ""


class BrandKitIn(BaseModel):
    name: str
    slug: str | None = None
    industry: str = ""
    tagline: str = ""
    voice: Voice = Voice()
    colors: dict = {}
    font_stack: str = ""
    aesthetic: list[str] = []
    logo_svg: str | None = None


@router.get("")
def list_brand_kits():
    return {"brand_kits": brand_kits.list_kits()}


@router.post("")
def create_brand_kit(payload: BrandKitIn):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    data = payload.model_dump()
    logo = data.pop("logo_svg", None)
    return brand_kits.save_kit(data, logo)


@router.delete("/{slug}")
def delete_brand_kit(slug: str):
    if not brand_kits.delete_kit(slug):
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return {"deleted": slug}


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
