import asyncio
import logging
from backend.database import SessionLocal
from backend.orchestrator.pipeline import BuildPipeline

logger = logging.getLogger(__name__)


class JobQueue:
    """Simple in-process async job queue."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("JobQueue worker started")

    def stop(self):
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

    async def enqueue(self, build_id: str):
        await self._queue.put(build_id)
        logger.info("Build %s enqueued (queue size: %d)", build_id, self._queue.qsize())

    async def _worker(self):
        while True:
            try:
                build_id = await self._queue.get()
                logger.info("Processing build %s", build_id)
                db = SessionLocal()
                try:
                    pipeline = BuildPipeline(db)
                    await pipeline.run(build_id)
                except Exception as e:
                    logger.exception("Worker error for build %s: %s", build_id, e)
                finally:
                    db.close()
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("JobQueue worker cancelled")
                break
            except Exception as e:
                logger.exception("Unexpected worker loop error: %s", e)


job_queue = JobQueue()
