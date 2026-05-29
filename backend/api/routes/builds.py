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
