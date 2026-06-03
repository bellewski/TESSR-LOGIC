"""Knowledge Library API — browse/search/edit the cross-domain recipe library."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import library

router = APIRouter(prefix="/library", tags=["library"])


class EntryIn(BaseModel):
    id: str | None = None
    domain: str
    title: str
    tags: list[str] = []
    stack: list[str] = []
    when: str = ""
    principle: str = ""
    exemplar: str = ""
    pitfalls: str = ""


@router.get("")
def list_library(domain: str | None = None):
    return {"domains": library.list_domains(), "entries": library.list_entries(domain)}


@router.post("")
def create_entry(payload: EntryIn):
    if not payload.title.strip() or not payload.domain.strip():
        raise HTTPException(status_code=400, detail="domain and title are required")
    return library.save_entry(payload.model_dump())


@router.put("/{entry_id}")
def update_entry(entry_id: str, payload: EntryIn):
    data = payload.model_dump()
    data["id"] = entry_id
    return library.save_entry(data)


@router.delete("/{entry_id}")
def remove_entry(entry_id: str):
    if not library.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Library entry not found")
    return {"deleted": entry_id}


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
