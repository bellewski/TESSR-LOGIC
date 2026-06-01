from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from pathlib import Path
import re
from backend.database import get_db
from backend.schemas.build import BuildCreate, BuildRead, BuildList
from backend.schemas.event import BuildEventList
from backend.schemas.file_record import GeneratedFileList
from backend.schemas.finding import FindingList
from backend.schemas.project_context import BuildDirectoryConfigRead
from backend.services.build_service import BuildService
from backend.config import settings
from backend.agents.builder import cleanup_build_procs

router = APIRouter(prefix="/builds", tags=["builds"])


@router.post("", response_model=BuildRead, status_code=201)
async def create_build(payload: BuildCreate, db: Session = Depends(get_db)):
    svc = BuildService(db)
    build = await svc.create_and_enqueue(
        project_name=payload.project_name,
        requirement=payload.requirement,
        stack_target=payload.stack_target,
        mode=payload.mode.value,
        project_context_id=payload.project_context_id,
        prompt_template_id=payload.prompt_template_id,
        source_dir=payload.source_dir,
        workspace_dir=payload.workspace_dir,
        output_dir=payload.output_dir,
    )
    return build


@router.get("/{build_id}/directories", response_model=BuildDirectoryConfigRead)
def get_build_directories(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    if not svc.get_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    cfg = svc.get_directory_config(build_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="No directory config for this build")
    return cfg


@router.get("", response_model=BuildList)
def list_builds(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    svc = BuildService(db)
    builds, total = svc.list_builds(skip, limit)
    return BuildList(builds=builds, total=total)


@router.get("/{build_id}", response_model=BuildRead)
def get_build(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    build = svc.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return build


@router.get("/{build_id}/events", response_model=BuildEventList)
def list_build_events(build_id: str, skip: int = 0, limit: int = 200, db: Session = Depends(get_db)):
    svc = BuildService(db)
    if not svc.get_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    events, total = svc.list_events(build_id, skip, limit)
    return BuildEventList(events=events, total=total)


@router.get("/{build_id}/files", response_model=GeneratedFileList)
def list_build_files(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    if not svc.get_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    files, total = svc.list_files(build_id)
    return GeneratedFileList(files=files, total=total)


@router.get("/{build_id}/findings", response_model=FindingList)
def list_build_findings(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    if not svc.get_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    findings, total = svc.list_findings(build_id)
    return FindingList(findings=findings, total=total)


@router.post("/{build_id}/cancel", response_model=BuildRead)
def cancel_build(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    build = svc.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    # Idempotent: if already cancelled, return it
    if build.status == "failed" and build.error_message and "cancelled" in build.error_message.lower():
        return build
    if build.status not in ("queued", "running"):
        raise HTTPException(status_code=400, detail=f"Build is {build.status}, cannot cancel")
    cancelled = svc.cancel_build(build_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Build not found")
    cleanup_build_procs(build_id)
    return cancelled


@router.post("/{build_id}/rerun", response_model=BuildRead, status_code=201)
async def rerun_build(build_id: str, db: Session = Depends(get_db)):
    svc = BuildService(db)
    original = svc.get_build(build_id)
    if not original:
        raise HTTPException(status_code=404, detail="Build not found")
    cfg = svc.get_directory_config(build_id)
    new_build = await svc.create_and_enqueue(
        project_name=original.project_name,
        requirement=original.requirement,
        stack_target=original.stack_target,
        mode=original.mode,
        project_context_id=cfg.project_context_id if cfg else None,
        prompt_template_id=cfg.prompt_template_id if cfg else None,
        source_dir=cfg.source_dir if cfg else None,
        workspace_dir=cfg.workspace_dir if cfg else None,
        output_dir=cfg.output_dir if cfg else None,
    )
    return new_build


@router.delete("/{build_id}")
def delete_build(build_id: str, db: Session = Depends(get_db)):
    """Delete a build and its workspace files."""
    import shutil
    svc = BuildService(db)
    build = svc.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    cfg = svc.get_directory_config(build_id)
    workspace_base = Path(cfg.workspace_dir) if cfg and cfg.workspace_dir else Path(settings.workspace_path)
    build_folder = workspace_base / build_id
    if build_folder.exists():
        try:
            shutil.rmtree(build_folder)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not delete build files: {e}")
    svc.delete_build(build_id)
    return {"deleted": True, "id": build_id}



def open_build_folder(build_id: str, db: Session = Depends(get_db)):
    """Open the build's src/ folder in Windows Explorer / macOS Finder."""
    import subprocess, sys, platform
    from backend.config import get_settings
    settings = get_settings()
    svc = BuildService(db)
    build = svc.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    cfg = svc.get_directory_config(build_id)
    workspace_base = Path(cfg.workspace_dir) if cfg and cfg.workspace_dir else Path(settings.workspace_path)
    # Try src/ first, fall back to build root
    src_dir = workspace_base / build_id / "src"
    if not src_dir.exists():
        src_dir = workspace_base / build_id
    if not src_dir.exists():
        raise HTTPException(status_code=404, detail=f"Build folder not found: {src_dir}")
    try:
        os_name = platform.system()
        if os_name == "Windows":
            subprocess.Popen(["explorer", str(src_dir)])
        elif os_name == "Darwin":
            subprocess.Popen(["open", str(src_dir)])
        else:
            subprocess.Popen(["xdg-open", str(src_dir)])
        return {"opened": True, "path": str(src_dir)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not open folder: {e}")


@router.get("/{build_id}/serve")
@router.get("/{build_id}/serve/{path:path}")
def serve_build_file(request: Request, build_id: str, path: str = "", db: Session = Depends(get_db)):
    """Serve static files from a build's src/ directory.

    GET /builds/{build_id}/serve       -> redirects to index.html
    GET /builds/{build_id}/serve/      -> serves index.html
    GET /builds/{build_id}/serve/app.js -> serves app.js
    """
    svc = BuildService(db)
    if not svc.get_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")

    cfg = svc.get_directory_config(build_id)
    workspace_base = Path(cfg.workspace_dir) if cfg and cfg.workspace_dir else Path(settings.workspace_path)
    build_root = workspace_base / build_id

    # Search for src/ with HTML files — check all possible locations
    src_dir = None
    build_root_resolved = build_root.resolve()
    
    # Collect all candidate src directories
    candidates_dirs = []
    
    # 1. Direct src/
    candidates_dirs.append(build_root / "src")
    
    # 2. round_N/src/ directories sorted highest first
    round_dirs = sorted(
        [d for d in build_root.iterdir() if d.is_dir() and d.name.startswith("round_")],
        key=lambda d: int(d.name.split("_")[1]) if d.name.split("_")[1].isdigit() else 0,
        reverse=True
    ) if build_root.exists() else []
    for rd in round_dirs:
        candidates_dirs.append(rd / "src")
        candidates_dirs.append(rd)  # also try round dir itself

    # 3. Build root itself as last resort
    candidates_dirs.append(build_root)

    for candidate in candidates_dirs:
        if candidate.exists() and candidate.is_dir():
            html_files = list(candidate.rglob("*.html"))
            if html_files:
                src_dir = candidate.resolve()
                print(f"Serve: found {len(html_files)} HTML files in {src_dir}")
                break

    if src_dir is None:
        raise HTTPException(status_code=404, detail=f"No HTML files found in build {build_id}")

    # Security: ensure we never leave the build directory
    try:
        Path(src_dir).relative_to(build_root_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not src_dir.exists() or not src_dir.is_dir():
        raise HTTPException(status_code=404, detail="Build src directory not found")

    # Redirect /serve to /serve/ so relative asset paths in HTML resolve correctly
    if not path and not request.url.path.endswith("/"):
        return RedirectResponse(url=f"/builds/{build_id}/serve/")

    # Default to index.html for root /serve/ requests — search anywhere under src/
    if not path or path.endswith("/"):
        candidates = list(src_dir.rglob("index.html"))
        if candidates:
            rel = candidates[0].relative_to(src_dir).as_posix()
            path = path.rstrip("/") + "/" + rel if path else rel
        else:
            path = path.rstrip("/") + "/index.html" if path else "index.html"

    target = (src_dir / path).resolve()

    # Security: ensure target is inside src_dir
    try:
        target.relative_to(src_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # For HTML files, rewrite absolute asset paths to relative so they resolve
    # correctly when served from /builds/{id}/serve/
    if target.suffix.lower() == ".html":
        content = target.read_text(encoding="utf-8", errors="replace")
        # Rewrite href="/path/to/file" -> href="path/to/file"
        # Rewrite src="/path/to/file" -> src="path/to/file"
        rewritten = re.sub(
            r'((?:href|src)\s*=\s*")/([^"]+)"',
            r'\1\2"',
            content,
        )
        if rewritten != content:
            return Response(content=rewritten, media_type="text/html")

    return FileResponse(path=target)


# ── Workshop: post-build editing (manual + LLM-assisted) ────────────────────

from pydantic import BaseModel


class WorkshopSave(BaseModel):
    path: str          # relative path within the build's src/
    content: str


class WorkshopEdit(BaseModel):
    path: str
    instruction: str


def _resolve_editable_src(build_id: str, db: Session) -> Path:
    """Return the canonical, editable src directory for a build.

    Prefers build_root/src (where the winning round is published on completion),
    then the highest round_N/src, then build_root itself."""
    cfg = BuildService(db).get_directory_config(build_id)
    workspace_base = Path(cfg.workspace_dir) if cfg and cfg.workspace_dir else Path(settings.workspace_path)
    build_root = workspace_base / build_id
    if not build_root.exists():
        raise HTTPException(status_code=404, detail=f"Build folder not found for {build_id}")

    candidates = [build_root / "src"]
    round_dirs = sorted(
        [d for d in build_root.iterdir() if d.is_dir() and d.name.startswith("round_")],
        key=lambda d: int(d.name.split("_")[1]) if d.name.split("_")[1].isdigit() else 0,
        reverse=True,
    )
    for rd in round_dirs:
        candidates.append(rd / "src")
    candidates.append(build_root)

    for c in candidates:
        if c.exists() and c.is_dir() and any(p.is_file() for p in c.rglob("*")):
            return c.resolve()
    raise HTTPException(status_code=404, detail="No editable source files found for this build")


def _safe_target(src_dir: Path, rel_path: str) -> Path:
    """Resolve rel_path within src_dir, rejecting traversal."""
    target = (src_dir / rel_path).resolve()
    try:
        target.relative_to(src_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path escapes build directory")
    return target


@router.get("/{build_id}/workshop/files")
def workshop_list_files(build_id: str, db: Session = Depends(get_db)):
    """List all editable files in a build with their relative paths and sizes."""
    src_dir = _resolve_editable_src(build_id, db)
    files = []
    for p in sorted(src_dir.rglob("*")):
        if p.is_file():
            files.append({
                "relative_path": p.relative_to(src_dir).as_posix(),
                "size_bytes": p.stat().st_size,
            })
    return {"files": files, "total": len(files), "src_dir": str(src_dir)}


@router.get("/{build_id}/workshop/file")
def workshop_read_file(build_id: str, path: str, db: Session = Depends(get_db)):
    """Read a single editable file's content by relative path."""
    src_dir = _resolve_editable_src(build_id, db)
    target = _safe_target(src_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="replace")}


@router.put("/{build_id}/workshop/file")
def workshop_save_file(build_id: str, payload: WorkshopSave, db: Session = Depends(get_db)):
    """Write edited content back to a build file (and re-publish to output dir if configured)."""
    src_dir = _resolve_editable_src(build_id, db)
    target = _safe_target(src_dir, payload.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")

    # Mirror the edit into the configured output directory if one exists
    cfg = BuildService(db).get_directory_config(build_id)
    if cfg and cfg.output_dir:
        try:
            out_root = Path(cfg.output_dir) / build_id / "src"
            dest = out_root / payload.path
            if out_root.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(payload.content, encoding="utf-8")
        except Exception:
            pass  # output mirror is best-effort

    return {"saved": True, "path": payload.path, "size_bytes": len(payload.content)}


@router.post("/{build_id}/workshop/edit")
async def workshop_llm_edit(build_id: str, payload: WorkshopEdit, db: Session = Depends(get_db)):
    """Apply a natural-language edit to a file via the LLM. Returns the proposed
    new content WITHOUT saving — the UI previews it, then PUTs to save."""
    from backend.providers.ollama_provider import OllamaProvider
    from backend.providers.base import ModelRequest

    src_dir = _resolve_editable_src(build_id, db)
    target = _safe_target(src_dir, payload.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    current = target.read_text(encoding="utf-8", errors="replace")
    ext = target.suffix.lstrip(".") or "txt"

    provider = OllamaProvider(agent_type="coder")
    system = (
        "You are a precise code editor. You are given the FULL contents of a single file "
        "and an instruction. Apply ONLY the requested change while preserving everything else "
        "that should stay. Return the COMPLETE updated file — every line — and NOTHING else: "
        "no explanations, no commentary, no markdown code fences."
    )
    prompt = (
        f"File: {payload.path}\n"
        f"Language/type: {ext}\n\n"
        f"=== CURRENT FILE CONTENTS ===\n{current}\n=== END ===\n\n"
        f"INSTRUCTION: {payload.instruction}\n\n"
        f"Return the complete updated contents of {payload.path} now."
    )

    resp = await provider.complete(ModelRequest(
        prompt=prompt, system_prompt=system, temperature=0.2, max_tokens=16384,
    ))
    if not resp.success:
        raise HTTPException(status_code=502, detail=f"LLM edit failed: {resp.error}")

    new_content = resp.content.strip()
    # Strip accidental markdown fences the model may add despite instructions
    if new_content.startswith("```"):
        nl = new_content.find("\n")
        if nl != -1:
            new_content = new_content[nl + 1:]
        if new_content.rstrip().endswith("```"):
            new_content = new_content.rstrip()[:-3]
        new_content = new_content.strip("\n")

    return {"path": payload.path, "original": current, "proposed": new_content, "model": resp.model}


class WorkshopAssist(BaseModel):
    message: str


@router.post("/{build_id}/workshop/assist")
async def workshop_assist(build_id: str, payload: WorkshopAssist, db: Session = Depends(get_db)):
    """Conversational, project-level editor (dummy-proof). The user describes what they want
    in plain language; the LLM decides which files to change, edits across the whole project,
    applies the changes, and returns a plain-English summary + the list of changed files.
    No file selection needed."""
    from backend.providers.ollama_provider import OllamaProvider
    from backend.providers.base import ModelRequest

    src_dir = _resolve_editable_src(build_id, db)
    editable_exts = {".html", ".css", ".js", ".ts", ".json", ".md", ".txt", ".py"}
    files = sorted(p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in editable_exts)
    if not files:
        raise HTTPException(status_code=404, detail="No editable files found for this project")

    # Budgeted snapshot of the whole project so the LLM can choose what to change.
    listing, bodies, used, budget = [], [], 0, 48000
    for p in files:
        rel = p.relative_to(src_dir).as_posix()
        listing.append(rel)
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        block = f"===FILE: {rel}===\n{txt}\n===END===\n"
        if used + len(block) <= budget:
            bodies.append(block)
            used += len(block)

    system = (
        "You are an expert web developer making changes to an EXISTING project on behalf of a "
        "non-technical user. They describe what they want in plain language; YOU decide which "
        "file(s) to change and make every edit needed across the project — the user should not "
        "have to name files. Preserve everything that already works. Keep the site runnable: "
        "guard every element lookup (a shared script runs on all pages), never break existing "
        "features, no external/CDN dependencies. "
        "Respond with EXACTLY this format: first a single line starting 'SUMMARY: ' describing in "
        "plain English what you changed, then ONLY the files you changed, each as a COMPLETE file:\n"
        "===FILE: relative/path.ext===\n<full updated file>\n===END===\n"
        "Return only files you actually changed. No other prose, no markdown fences."
    )
    prompt = (
        f"Project '{build_id}' files:\n- " + "\n- ".join(listing) + "\n\n"
        f"Current contents:\n" + "".join(bodies) + "\n"
        f"{'='*60}\nUSER REQUEST: {payload.message}\n{'='*60}\n\n"
        "Make the change now. SUMMARY line first, then only the changed files."
    )

    resp = await OllamaProvider(agent_type="coder").complete(ModelRequest(
        prompt=prompt, system_prompt=system, temperature=0.3, max_tokens=16384,
    ))
    if not resp.success:
        raise HTTPException(status_code=502, detail=f"Assistant failed: {resp.error}")

    content = resp.content or ""
    m = re.search(r"SUMMARY:\s*(.+)", content)
    summary = m.group(1).strip()[:400] if m else ""

    # Parse + write changed files (===FILE:=== blocks), path-guarded.
    changed = []
    parts = re.split(r"===FILE:\s*", content)
    cfg = BuildService(db).get_directory_config(build_id)
    out_root = (Path(cfg.output_dir) / build_id / "src") if (cfg and cfg.output_dir) else None
    for part in parts[1:]:
        header, _, body = part.partition("\n")
        rel = header.replace("===", "").strip()
        body = re.split(r"===END===|===FILE:", body)[0]
        body = re.sub(r"^```\w*\n", "", body)
        body = re.sub(r"\n```\s*$", "", body)
        body = body.strip("\n")
        if not rel or len(body) < 5:
            continue
        try:
            target = _safe_target(src_dir, rel)
        except HTTPException:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        changed.append(rel)
        if out_root and out_root.exists():  # mirror to output dir
            try:
                dest = out_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(body, encoding="utf-8")
            except Exception:
                pass

    if not changed:
        return {
            "summary": summary or "I couldn't apply a concrete change to that request. Try being more specific (e.g. 'make the header purple and the buttons rounded').",
            "changed_files": [],
            "applied": False,
        }
    return {
        "summary": summary or f"Updated {len(changed)} file(s): {', '.join(changed)}",
        "changed_files": changed,
        "applied": True,
    }
