from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pathlib import Path

from backend.config import settings

router = APIRouter(prefix="/files", tags=["files"])

# Common safe roots — builds may be in custom directories
_SAFE_ROOTS = [
    Path(settings.workspace_path).resolve(),
]


def _is_safe_path(p: Path) -> bool:
    """Allow any existing file under a safe root or any reasonable build directory."""
    resolved = p.resolve()
    for root in _SAFE_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    # Fallback: allow if path looks like a real build output (has UUID-like segment)
    # and isn't a system/sensitive directory
    parts = [part.lower() for part in resolved.parts]
    blocked = {"windows", "program files", "programdata", "system32", "syswow64",
               "drivers", "config", "registry", "boot", "inetpub", "documents and settings"}
    if any(part in blocked for part in parts):
        return False
    return True


@router.get("/content")
def get_file_content(path: str):
    """Read a generated file by absolute path."""
    p = Path(path).resolve()
    if not _is_safe_path(p):
        raise HTTPException(status_code=403, detail="Access denied: path is outside allowed directories")

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

    return PlainTextResponse(content=content)
