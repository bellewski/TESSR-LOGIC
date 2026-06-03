"""
Knowledge Library — cross-domain, offline grounding for the agents.

A curated set of vetted, reusable RECIPES (one JSON file each) spanning every kind of build:
UI, frontend, backend/APIs, databases, auth/security, AI-agent loops, servers/devops, mobile/PWA,
data & sensor diagnostics, CLI, testing. Agents retrieve the recipes relevant to the current build
and use them as REFERENCE EXEMPLARS — so they go in knowing what good looks like instead of
inventing from a cold base model.

Recipes are PRINCIPLES + illustrative exemplars to ADAPT, never fixed templates — the model still
writes everything. Retrieval is keyword/tag based (deterministic, fully offline, no embed model
required); if the embedding memory layer is active it can additionally rank semantically.

Library lives at repo-root/library/<domain>/<id>.json. Drop in a new JSON file and it's available.
"""
import json
import re
import logging
from pathlib import Path
from functools import lru_cache

from backend.config import settings

logger = logging.getLogger(__name__)

_LIB_DIR = Path(settings.workspace_path).resolve().parent.parent / "library"

# Map a build's stack_family / archetype to the library domains worth retrieving.
STACK_DOMAINS = {
    "web": ["ui", "frontend"],
    "fullstack": ["ui", "frontend", "backend", "database", "auth"],
    "api": ["backend", "database", "auth"],
    "node": ["backend", "database"],
    "python": ["backend", "database", "data"],
    "cli": ["cli"],
    "mobile": ["mobile", "ui"],
    "agent": ["ai-agents"],
    "data": ["data", "database"],
    "automation": ["data", "backend"],
}


@lru_cache(maxsize=1)
def _load_all() -> list[dict]:
    out = []
    if not _LIB_DIR.exists():
        return out
    for f in _LIB_DIR.glob("*/*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            rec.setdefault("domain", f.parent.name)
            rec.setdefault("id", f.stem)
            out.append(rec)
        except Exception as e:
            logger.warning("Library: bad entry %s: %s", f, e)
    return out


def reload():
    _load_all.cache_clear()


def list_entries(domain: str | None = None) -> list[dict]:
    items = _load_all()
    if domain:
        items = [e for e in items if e.get("domain") == domain]
    # light summaries (no big exemplar bodies)
    return [{"id": e["id"], "domain": e.get("domain"), "title": e.get("title", ""),
             "tags": e.get("tags", []), "when": e.get("when", ""), "stack": e.get("stack", [])}
            for e in items]


def list_domains() -> list[str]:
    return sorted({e.get("domain", "") for e in _load_all() if e.get("domain")})


def get(entry_id: str) -> dict | None:
    return next((e for e in _load_all() if e.get("id") == entry_id), None)


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall((s or "").lower()))


def search(query: str, domains: list[str] | None = None, k: int = 4) -> list[dict]:
    """Return up to k most relevant recipes for the query (tag/keyword scored, offline)."""
    q = _tokens(query)
    if not q:
        return []
    scored = []
    for e in _load_all():
        if domains and e.get("domain") not in domains:
            continue
        tagtok = _tokens(" ".join(e.get("tags", [])))
        titletok = _tokens(e.get("title", ""))
        whentok = _tokens(e.get("when", "")) | _tokens(" ".join(e.get("stack", [])))
        score = 3 * len(q & tagtok) + 2 * len(q & titletok) + 1 * len(q & whentok)
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:k]]


def exemplars_block(query: str, domains: list[str] | None = None, k: int = 3) -> str:
    """Render retrieved recipes as a REFERENCE EXEMPLARS prompt block for an agent."""
    hits = search(query, domains, k)
    if not hits:
        return ""
    parts = [
        "\n=== REFERENCE EXEMPLARS (vetted patterns from the knowledge library — ADAPT them to "
        "this project, do NOT copy verbatim; they show what GOOD looks like) ==="
    ]
    for e in hits:
        block = f"\n[{e.get('domain')}] {e.get('title','')}"
        if e.get("when"):
            block += f"\nUse when: {e['when']}"
        if e.get("principle"):
            block += f"\nPrinciple: {e['principle']}"
        ex = e.get("exemplar")
        if isinstance(ex, list):
            ex = "\n".join(str(x) for x in ex)
        if ex:
            block += f"\nExemplar:\n{ex}"
        if e.get("pitfalls"):
            block += f"\nAvoid: {e['pitfalls']}"
        parts.append(block)
    return "\n".join(parts)
