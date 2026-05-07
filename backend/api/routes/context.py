from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.project_context import (
    ProjectContextCreate, ProjectContextUpdate, ProjectContextRead,
    ScanRequest, ScanResult, FileManifestEntryRead,
)
from backend.services.scanner_service import ProjectContextService

router = APIRouter(prefix="/contexts", tags=["project-context"])


@router.post("", response_model=ProjectContextRead, status_code=201)
def create_context(payload: ProjectContextCreate, db: Session = Depends(get_db)):
    svc = ProjectContextService(db)
    ctx = svc.create(
        name=payload.name,
        source_dir=payload.source_dir,
        workspace_dir=payload.workspace_dir,
        output_dir=payload.output_dir,
    )
    return ctx


@router.get("", response_model=list[ProjectContextRead])
def list_contexts(db: Session = Depends(get_db)):
    return ProjectContextService(db).list_all()


@router.get("/{context_id}", response_model=ProjectContextRead)
def get_context(context_id: str, db: Session = Depends(get_db)):
    ctx = ProjectContextService(db).get(context_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    return ctx


@router.patch("/{context_id}", response_model=ProjectContextRead)
def update_context(context_id: str, payload: ProjectContextUpdate, db: Session = Depends(get_db)):
    svc = ProjectContextService(db)
    ctx = svc.update(context_id, **payload.model_dump(exclude_none=True))
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    return ctx


@router.delete("/{context_id}", status_code=204)
def delete_context(context_id: str, db: Session = Depends(get_db)):
    from backend.models.project_context import ProjectContext, FileManifestEntry
    db.query(FileManifestEntry).filter(FileManifestEntry.context_id == context_id).delete()
    ctx = db.query(ProjectContext).filter(ProjectContext.id == context_id).first()
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    db.delete(ctx)
    db.commit()


@router.post("/{context_id}/scan", response_model=ScanResult)
def scan_context(context_id: str, payload: ScanRequest, db: Session = Depends(get_db)):
    svc = ProjectContextService(db)
    ctx = svc.get(context_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found")
    try:
        result = svc.scan(context_id, payload.source_dir)
        return ScanResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@router.post("/scan", response_model=ScanResult)
def quick_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    """Scan a directory and create a new context in one step."""
    from backend.services.scanner_service import scan_folder
    try:
        result = scan_folder(payload.source_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    svc = ProjectContextService(db)
    import os
    ctx_name = os.path.basename(payload.source_dir.rstrip("/\\")) or "scanned-project"
    ctx = svc.create(name=ctx_name, source_dir=payload.source_dir)
    full_result = svc.scan(ctx.id, payload.source_dir)
    return ScanResult(**full_result)


@router.get("/{context_id}/manifest", response_model=list[FileManifestEntryRead])
def get_manifest(context_id: str, db: Session = Depends(get_db)):
    svc = ProjectContextService(db)
    if not svc.get(context_id):
        raise HTTPException(status_code=404, detail="Context not found")
    return svc.get_manifest(context_id)
