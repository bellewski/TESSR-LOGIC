import asyncio
import logging
import time
from datetime import datetime, timezone
from backend.database import SessionLocal
from backend.orchestrator.pipeline import BuildPipeline

logger = logging.getLogger(__name__)

# Watchdog tuning.
WATCHDOG_INTERVAL = 60          # seconds between health sweeps
STALL_MINUTES = 20             # a 'running' build with no DB update for this long is considered hung


class JobQueue:
    """Simple in-process async job queue with a self-healing watchdog."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._running = False
        self._restart_count = 0
        self._current_build: str | None = None   # build the worker is actively processing
        self._current_started: float = 0.0        # monotonic start time of current build

    def start(self):
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())
            self._watchdog_task = asyncio.create_task(self._watchdog())
            logger.info("JobQueue worker + watchdog started")

    def stop(self):
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

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
                self._current_build = build_id
                self._current_started = time.monotonic()
                db = SessionLocal()
                try:
                    pipeline = BuildPipeline(db)
                    await pipeline.run(build_id)
                    logger.info("Completed processing build %s", build_id)
                except Exception as e:
                    logger.exception("Worker error for build %s: %s", build_id, e)
                finally:
                    db.close()
                    self._current_build = None
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("JobQueue worker cancelled")
                break
            except Exception as e:
                logger.exception("Unexpected worker loop error: %s", e)
                await asyncio.sleep(1)  # Prevent rapid error loops
        logger.info("JobQueue worker loop ended")

    async def _watchdog(self):
        """Self-healing health monitor. Periodically:
          1. Revives the worker task if it died unexpectedly.
          2. Re-enqueues 'queued' builds that aren't actually in the in-memory queue
             (the class of bug where a build sits Queued forever — e.g. enqueue lost,
             or created while the worker was momentarily down).
          3. Recovers 'running' builds that are NOT being processed by this worker
             (orphaned by a crash/restart) — resets them to queued and re-enqueues.
          4. Flags a build that IS being processed but has shown no DB progress for
             STALL_MINUTES (a hung model call); resets and re-enqueues it so the
             pipeline restarts that build instead of hanging forever.
        """
        from backend.models.build import Build, BuildStatus
        logger.info("JobQueue watchdog started (interval=%ss, stall=%smin)", WATCHDOG_INTERVAL, STALL_MINUTES)
        while self._running:
            try:
                await asyncio.sleep(WATCHDOG_INTERVAL)
                # (1) revive a dead worker
                if self._worker_task is None or self._worker_task.done():
                    logger.warning("Watchdog: worker task not alive — restarting")
                    self._worker_task = asyncio.create_task(self._worker())

                db = SessionLocal()
                try:
                    now = datetime.now(timezone.utc)
                    requeue: list[str] = []
                    queued = db.query(Build).filter(Build.status == BuildStatus.queued).all()
                    running = db.query(Build).filter(Build.status == BuildStatus.running).all()

                    # (2) queued builds the worker isn't going to see (queue drained / lost)
                    if queued and self._queue.qsize() == 0 and self._current_build is None:
                        for b in queued:
                            requeue.append(b.id)

                    # (3)+(4) running builds that are orphaned or hung
                    for b in running:
                        if b.id == self._current_build:
                            # actively processing — only act if clearly hung (no progress)
                            stalled = (time.monotonic() - self._current_started) > STALL_MINUTES * 60
                            try:
                                last = datetime.fromisoformat(str(b.updated_at))
                                if last.tzinfo is None:
                                    last = last.replace(tzinfo=timezone.utc)
                                stalled = stalled and (now - last).total_seconds() > STALL_MINUTES * 60
                            except Exception:
                                pass
                            if stalled:
                                logger.warning("Watchdog: build %s appears HUNG (>%smin no progress) — resetting", b.id, STALL_MINUTES)
                                b.status = BuildStatus.queued
                                requeue.append(b.id)
                        else:
                            # 'running' in DB but not the worker's current build → orphaned
                            logger.warning("Watchdog: orphaned running build %s — resetting to queued", b.id)
                            b.status = BuildStatus.queued
                            requeue.append(b.id)

                    if requeue:
                        db.commit()
                finally:
                    db.close()

                for bid in dict.fromkeys(requeue):  # dedupe, preserve order
                    await self.enqueue(bid)
                    logger.info("Watchdog: re-enqueued build %s", bid)
            except asyncio.CancelledError:
                logger.info("JobQueue watchdog cancelled")
                break
            except Exception as e:
                logger.exception("Watchdog sweep error: %s", e)
        logger.info("JobQueue watchdog ended")


job_queue = JobQueue()
