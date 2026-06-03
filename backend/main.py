import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.database import init_db
from backend.orchestrator.job_queue import job_queue
from backend.api.routes import builds, settings as settings_router, ollama, files, context, prompts, agents as agents_router, connectors as connectors_router, brand_kits as brand_kits_router, plugins as plugins_router
from backend.api.websocket import router as ws_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)
    init_db()
    # Seed builtin agent configs on startup
    try:
        from backend.database import SessionLocal
        from backend.repositories.agent_config_repo import AgentConfigRepository
        db = SessionLocal()
        try:
            AgentConfigRepository(db).seed_builtin()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to seed builtin agents: %s", e)
    job_queue.start()
    # Recover orphaned builds: a restart clears the in-memory queue, so any build left in
    # 'queued' (or interrupted mid-'running') would otherwise sit forever. Re-enqueue them.
    try:
        from backend.database import SessionLocal
        from backend.models.build import Build, BuildStatus
        db = SessionLocal()
        try:
            orphaned = (
                db.query(Build)
                .filter(Build.status.in_([BuildStatus.queued, BuildStatus.running]))
                .all()
            )
            for b in orphaned:
                b.status = BuildStatus.queued  # reset interrupted 'running' back to queued
            if orphaned:
                db.commit()
            ids = [b.id for b in orphaned]
        finally:
            db.close()
        for bid in ids:
            await job_queue.enqueue(bid)
            logger.info("Recovered orphaned build %s on startup", bid)
    except Exception as e:
        logger.warning("Build recovery on startup failed: %s", e)
    yield
    logger.info("Shutting down %s", settings.app_name)
    job_queue.stop()


app = FastAPI(
    title=settings.app_name,
    description="Multi-agent coding factory — local-first MVP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(builds.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(ollama.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(context.router, prefix="/api")
app.include_router(prompts.router, prefix="/api")
app.include_router(agents_router.router, prefix="/api")
app.include_router(connectors_router.router, prefix="/api")
app.include_router(brand_kits_router.router, prefix="/api")
app.include_router(plugins_router.router, prefix="/api")
app.include_router(ws_router)

# Serve built frontend static files (production mode — single port)
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets"), check_dir=False), name="assets")

    @app.get("/{path:path}")
    async def serve_index(path: str):
        """Serve index.html with no-cache so asset hashes are always fresh after rebuilds."""
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(
                str(index_path),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                }
            )
        return {"message": "TESSR-LOGIC API running", "frontend": "index.html not found"}
else:
    @app.get("/")
    async def root():
        return {"message": "TESSR-LOGIC API running", "frontend": "not built"}

@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
