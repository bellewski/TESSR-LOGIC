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
        self._restart_count = 0

    def start(self):
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("JobQueue worker started")

    def stop(self):
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

    async def restart_worker(self):
        """Force restart the worker if it gets stuck"""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        self._restart_count += 1
        logger.info("JobQueue worker restart #%d", self._restart_count)
        self._worker_task = asyncio.create_task(self._worker())

    async def enqueue(self, build_id: str):
        try:
            await self._queue.put(build_id)
            logger.info("Build %s enqueued (queue size: %d)", build_id, self._queue.qsize())
        except Exception as e:
            logger.error("Failed to enqueue build %s: %s", build_id, e)
            raise

    async def _worker(self):
        logger.info("JobQueue worker loop started")
        while self._running:
            try:
                # Use timeout to prevent hanging
                try:
                    build_id = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue  # Check if still running
                
                logger.info("Processing build %s", build_id)
                db = SessionLocal()
                try:
                    pipeline = BuildPipeline(db)
                    await pipeline.run(build_id)
                    logger.info("Completed processing build %s", build_id)
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
                await asyncio.sleep(1)  # Prevent rapid error loops
        logger.info("JobQueue worker loop ended")


job_queue = JobQueue()
