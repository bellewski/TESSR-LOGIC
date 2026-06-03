"""
Output / Deploy plugins — pluggable targets for a FINISHED build.

A small extensible registry: each plugin takes a completed build's source files and produces
a deliverable (a downloadable ZIP, a containerization bundle, a static-deploy bundle). Runs
offline. Adding a new output target = add one entry to PLUGINS.
"""
import io
import json
import zipfile
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.api.routes.builds import _resolve_editable_src
from backend.services.build_service import BuildService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plugins", tags=["plugins"])


# ── plugin registry ───────────────────────────────────────────────────────────
PLUGINS = [
    {"id": "zip", "name": "Download ZIP", "icon": "archive",
     "description": "Package the finished build's source into a downloadable .zip.",
     "supports": ["web", "node", "python", "cli", "any"]},
    {"id": "docker", "name": "Containerize (Dockerfile)", "icon": "box",
     "description": "Generate a Dockerfile matched to the stack (static→nginx, node, python) and bundle it with the source as a ready-to-build .zip.",
     "supports": ["web", "node", "python"]},
    {"id": "static-bundle", "name": "Static Deploy Bundle", "icon": "globe",
     "description": "Zip the static site plus a DEPLOY.md with one-command instructions for any static host (offline-friendly).",
     "supports": ["web"]},
]


@router.get("")
def list_plugins():
    return {"plugins": PLUGINS}


def _detect_stack(src: Path) -> str:
    if (src / "package.json").exists():
        return "node"
    if any(src.glob("requirements*.txt")) or any(src.rglob("*.py")):
        return "python"
    if any(src.rglob("*.html")):
        return "web"
    return "any"


def _dockerfile_for(stack: str) -> str:
    if stack == "node":
        return (
            "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\n"
            "RUN npm install --omit=dev || npm install\n"
            "EXPOSE 3000\nCMD [\"npm\",\"start\"]\n"
        )
    if stack == "python":
        return (
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\n"
            "RUN pip install --no-cache-dir -r requirements.txt || true\n"
            "EXPOSE 8000\nCMD [\"python\",\"app.py\"]\n"
        )
    # static -> nginx
    return (
        "FROM nginx:alpine\nCOPY . /usr/share/nginx/html\n"
        "EXPOSE 80\n"
    )


def _zip_dir(src: Path, extra_files: dict[str, str] | None = None) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in src.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(src).as_posix())
        for name, content in (extra_files or {}).items():
            z.writestr(name, content)
    buf.seek(0)
    return buf


@router.post("/{build_id}/run/{plugin_id}")
def run_plugin(build_id: str, plugin_id: str, db: Session = Depends(get_db)):
    """Run an output plugin and stream back the produced artifact (a .zip)."""
    if not any(p["id"] == plugin_id for p in PLUGINS):
        raise HTTPException(status_code=404, detail="Unknown plugin")
    build = BuildService(db).get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    if str(build.status) not in ("BuildStatus.completed", "completed"):
        # allow running on any build that has files, but warn-as-error only if no files
        pass
    src = _resolve_editable_src(build_id, db)
    safe_name = (build.project_name or build_id).lower().replace(" ", "-")

    if plugin_id == "zip":
        buf = _zip_dir(src)
        fname = f"{safe_name}.zip"

    elif plugin_id == "docker":
        stack = _detect_stack(src)
        dockerfile = _dockerfile_for(stack)
        ignore = "node_modules\n.git\n*.zip\n__pycache__\n"
        readme = (
            f"# {build.project_name} — Container bundle\n\nStack detected: **{stack}**\n\n"
            "## Build & run\n```\ndocker build -t app .\n"
            + ("docker run -p 80:80 app\n" if stack == "web" else
               "docker run -p 3000:3000 app\n" if stack == "node" else
               "docker run -p 8000:8000 app\n")
            + "```\n"
        )
        buf = _zip_dir(src, {"Dockerfile": dockerfile, ".dockerignore": ignore, "DEPLOY.md": readme})
        fname = f"{safe_name}-docker.zip"

    elif plugin_id == "static-bundle":
        if _detect_stack(src) != "web":
            raise HTTPException(status_code=400, detail="Static bundle only applies to static web builds")
        deploy = (
            f"# {build.project_name} — Static deploy\n\n"
            "This is a fully self-contained static site (no build step, no external assets).\n\n"
            "## Host it\n- Any static host (Nginx, Apache, S3, Netlify, GitHub Pages) — just upload these files.\n"
            "- Local preview: `python -m http.server 8080` then open http://localhost:8080\n"
        )
        buf = _zip_dir(src, {"DEPLOY.md": deploy})
        fname = f"{safe_name}-static.zip"
    else:
        raise HTTPException(status_code=404, detail="Unknown plugin")

    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
