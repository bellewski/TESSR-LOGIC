"""
Connectors — GitHub reference-pattern ingestion (online ingest -> offline build).

Flow (the "scrape + LLM chat + verify" tab):
  1. Fetch a public GitHub repo's file tree (online, this tab only).
  2. The LLM reads selected files and EXTRACTS REUSABLE PATTERNS — principles + short
     illustrative snippets + why they matter — NOT wholesale code copies. (Avoids license
     contamination; we keep lessons, not someone's codebase.)
  3. The user VERIFIES/approves the proposed patterns in the UI.
  4. Approved patterns are saved as a local "connector" (connectors/<slug>/connector.json)
     AND pushed into the offline memory layer as retrievable lessons, so the Coder/Architect
     learn from them on future builds — fully offline thereafter.

This is the ONLY component that touches the network. Builds remain air-gapped: they consume
the saved connectors/memory locally with zero egress.
"""
import re
import json
import time
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["connectors"])

# Local connector store at the repo root: connectors/<slug>/connector.json
_CONNECTORS_DIR = Path(settings.workspace_path).resolve().parent.parent / "connectors"
_CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)

_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".go", ".rs",
              ".java", ".rb", ".php", ".vue", ".svelte", ".sql", ".sh", ".md"}
_GH_RE = re.compile(r"github\.com[/:]([^/]+)/([^/#?.]+)")

# License risk classes for the "extract patterns, not code" guardrail.
_PERMISSIVE = {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "UNLICENSE",
               "CC0-1.0", "0BSD", "ZLIB", "MIT-0", "BSL-1.0"}
_COPYLEFT = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0",
             "GPL-2.0-ONLY", "GPL-3.0-ONLY", "AGPL-3.0-ONLY", "GPL-3.0-OR-LATER"}


def _classify_license(spdx: str | None) -> dict:
    s = (spdx or "").upper()
    if not s or s in ("NOASSERTION", "NONE", "NULL"):
        return {"spdx": spdx or "none", "risk": "none",
                "note": "No license = all rights reserved. Extract general PRINCIPLES only — never verbatim code."}
    if s in _COPYLEFT:
        return {"spdx": spdx, "risk": "copyleft",
                "note": "Copyleft (GPL/AGPL/etc.). Learn the approach but DO NOT save verbatim code — principles only, to avoid license contamination."}
    if s in _PERMISSIVE:
        return {"spdx": spdx, "risk": "permissive",
                "note": "Permissive license. Patterns are safe to learn from; attribution is good practice if you reuse anything substantial."}
    return {"spdx": spdx, "risk": "unknown",
            "note": "Unrecognized license — treat as restrictive: extract principles only."}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "connector"


def _parse_repo(url: str):
    m = _GH_RE.search(url or "")
    if not m:
        raise HTTPException(status_code=400, detail="Not a valid github.com repo URL")
    return m.group(1), m.group(2)


# ── models ──────────────────────────────────────────────────────────────────
class TreeReq(BaseModel):
    repo_url: str


class ExtractReq(BaseModel):
    repo_url: str
    paths: list[str]
    focus: str = ""        # optional: "auth flow", "chart rendering", etc.


class Pattern(BaseModel):
    title: str
    principle: str
    snippet: str = ""
    why: str = ""
    tags: str = ""


class SaveReq(BaseModel):
    name: str
    source_url: str
    focus: str = ""
    patterns: list[Pattern]
    license: dict = {}  # provenance: {spdx, risk, note} from the source repo


# ── GitHub fetch (online) ─────────────────────────────────────────────────────
@router.post("/github/tree")
async def github_tree(req: TreeReq):
    owner, repo = _parse_repo(req.repo_url)
    try:
        async with httpx.AsyncClient(timeout=20, headers={"Accept": "application/vnd.github+json"}) as c:
            meta = await c.get(f"https://api.github.com/repos/{owner}/{repo}")
            if meta.status_code == 404:
                raise HTTPException(status_code=404, detail="Repo not found (must be public)")
            meta.raise_for_status()
            meta_json = meta.json()
            branch = meta_json.get("default_branch", "main")
            lic = (meta_json.get("license") or {})
            license_info = _classify_license(lic.get("spdx_id"))
            tree = await c.get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
            tree.raise_for_status()
            data = tree.json()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 403:
            raise HTTPException(status_code=429, detail="GitHub rate limit hit (unauthenticated 60/hr). Try again later.")
        raise HTTPException(status_code=502, detail=f"GitHub error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {e}")

    files = [
        {"path": t["path"], "size": t.get("size", 0)}
        for t in data.get("tree", [])
        if t.get("type") == "blob"
        and Path(t["path"]).suffix.lower() in _CODE_EXTS
        and t.get("size", 0) < 120_000
    ]
    files.sort(key=lambda f: f["path"])
    return {"owner": owner, "repo": repo, "branch": branch, "files": files[:400],
            "truncated": data.get("truncated", False), "license": license_info}


async def _fetch_files(owner: str, repo: str, branch: str, paths: list[str], budget: int = 60_000):
    out, used = [], 0
    async with httpx.AsyncClient(timeout=20) as c:
        for p in paths[:25]:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{p}"
            try:
                r = await c.get(url)
                if r.status_code != 200:
                    continue
                txt = r.text
            except Exception:
                continue
            block = f"===FILE: {p}===\n{txt[:12000]}\n"
            if used + len(block) > budget:
                break
            out.append(block); used += len(block)
    return "".join(out)


@router.post("/github/extract")
async def github_extract(req: ExtractReq):
    """LLM reads the selected files and proposes reusable PATTERNS for the user to verify."""
    from backend.providers.ollama_provider import OllamaProvider
    from backend.providers.base import ModelRequest

    owner, repo = _parse_repo(req.repo_url)
    # need the branch again (cheap)
    async with httpx.AsyncClient(timeout=15, headers={"Accept": "application/vnd.github+json"}) as c:
        try:
            meta = await c.get(f"https://api.github.com/repos/{owner}/{repo}")
            branch = meta.json().get("default_branch", "main") if meta.status_code == 200 else "main"
        except Exception:
            branch = "main"

    corpus = await _fetch_files(owner, repo, branch, req.paths)
    if not corpus:
        raise HTTPException(status_code=404, detail="Could not fetch any of the selected files")

    system = (
        "You are a senior engineer extracting REUSABLE PATTERNS from a reference codebase so another "
        "AI can LEARN from them — you are NOT copying the code. For each distinct, transferable "
        "technique, output: a short title, the PRINCIPLE (what to do and when, in plain words), an "
        "OPTIONAL tiny illustrative snippet (<=8 lines, generic — not the verbatim file), and WHY it "
        "matters. Focus on patterns that improve how apps are built (structure, correctness, UX, "
        "security, performance). Ignore project-specific names. "
        "Return ONLY JSON: {\"patterns\":[{\"title\":\"\",\"principle\":\"\",\"snippet\":\"\",\"why\":\"\",\"tags\":\"\"}]}"
    )
    prompt = (
        (f"Focus area: {req.focus}\n\n" if req.focus else "")
        + f"Reference files from {owner}/{repo}:\n\n{corpus}\n\n"
        "Extract the reusable patterns now. JSON only."
    )
    resp = await OllamaProvider(agent_type="architect").complete(ModelRequest(
        prompt=prompt, system_prompt=system, temperature=0.2, max_tokens=2048, num_ctx=16384,
    ))
    if not resp.success:
        raise HTTPException(status_code=502, detail=f"Extraction failed: {resp.error}")

    from backend.agents.architect import _extract_json_object
    data = _extract_json_object(resp.content) or {}
    patterns = data.get("patterns") if isinstance(data, dict) else None
    if not isinstance(patterns, list):
        raise HTTPException(status_code=422, detail="Model did not return parseable patterns; try fewer/clearer files.")
    clean = []
    for p in patterns[:20]:
        if not isinstance(p, dict):
            continue
        clean.append({
            "title": str(p.get("title", ""))[:120],
            "principle": str(p.get("principle", ""))[:600],
            "snippet": str(p.get("snippet", ""))[:600],
            "why": str(p.get("why", ""))[:300],
            "tags": str(p.get("tags", ""))[:120],
        })
    return {"source": f"{owner}/{repo}", "patterns": clean}


# ── save / list / delete (offline) ────────────────────────────────────────────
@router.post("/save")
def save_connector(req: SaveReq):
    """Persist verified patterns as a connector AND seed them into the offline memory layer."""
    slug = _slug(req.name)
    cdir = _CONNECTORS_DIR / slug
    cdir.mkdir(parents=True, exist_ok=True)
    record = {
        "name": req.name, "slug": slug, "source_url": req.source_url, "focus": req.focus,
        "license": req.license or {}, "created_at": time.time(),
        "patterns": [p.model_dump() for p in req.patterns],
    }
    (cdir / "connector.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Feed verified patterns into the offline memory so agents learn from them on future builds.
    seeded = 0
    try:
        from backend.core.memory import get_memory
        mem = get_memory()
        for p in req.patterns:
            text = f"{p.title}: {p.principle}" + (f"\nWhy: {p.why}" if p.why else "") + (f"\nExample:\n{p.snippet}" if p.snippet else "")
            if mem.add("lesson", text, tags=f"connector {slug} {p.tags}".strip()):
                seeded += 1
    except Exception as e:
        logger.warning("Connector memory seeding failed: %s", e)

    return {"slug": slug, "saved_patterns": len(req.patterns), "memory_seeded": seeded,
            "memory_active": seeded > 0}


@router.get("")
def list_connectors():
    out = []
    for d in sorted(_CONNECTORS_DIR.glob("*/connector.json")):
        try:
            rec = json.loads(d.read_text(encoding="utf-8"))
            out.append({"name": rec.get("name"), "slug": rec.get("slug"),
                        "source_url": rec.get("source_url"), "focus": rec.get("focus"),
                        "license": rec.get("license", {}),
                        "pattern_count": len(rec.get("patterns", [])), "created_at": rec.get("created_at")})
        except Exception:
            continue
    out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return {"connectors": out}


@router.get("/{slug}")
def get_connector(slug: str):
    f = _CONNECTORS_DIR / _slug(slug) / "connector.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Connector not found")
    return json.loads(f.read_text(encoding="utf-8"))


@router.delete("/{slug}")
def delete_connector(slug: str):
    import shutil
    d = _CONNECTORS_DIR / _slug(slug)
    if not d.exists():
        raise HTTPException(status_code=404, detail="Connector not found")
    shutil.rmtree(d)
    return {"deleted": slug}
