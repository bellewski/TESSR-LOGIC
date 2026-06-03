"""Knowledge Library API — browse/search the cross-domain recipe library."""
from fastapi import APIRouter, HTTPException

from backend.core import library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("")
def list_library(domain: str | None = None):
    return {"domains": library.list_domains(), "entries": library.list_entries(domain)}


@router.get("/search")
def search_library(q: str, domain: str | None = None, k: int = 4):
    domains = [domain] if domain else None
    return {"results": library.search(q, domains, k)}


@router.get("/{entry_id}")
def get_entry(entry_id: str):
    e = library.get(entry_id)
    if not e:
        raise HTTPException(status_code=404, detail="Library entry not found")
    return e
