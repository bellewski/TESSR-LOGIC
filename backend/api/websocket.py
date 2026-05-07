import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.orchestrator.event_bus import event_bus
from backend.database import SessionLocal
from backend.repositories.event_repo import EventRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/builds/{build_id}/events")
async def build_events_ws(websocket: WebSocket, build_id: str):
    await websocket.accept()
    logger.info("WebSocket connected for build %s", build_id)

    # Send existing events first
    db = SessionLocal()
    try:
        repo = EventRepository(db)
        events, _ = repo.list_by_build(build_id)
        for ev in events:
            await websocket.send_text(json.dumps({
                "build_id": ev.build_id,
                "event_type": ev.event_type,
                "message": ev.message,
                "phase": ev.phase,
                "payload": ev.payload,
                "timestamp": ev.created_at.isoformat(),
            }))
    finally:
        db.close()

    queue = event_bus.subscribe(build_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                # Send heartbeat ping
                try:
                    await websocket.send_text(json.dumps({"event_type": "ping", "build_id": build_id}))
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for build %s", build_id)
    except Exception as e:
        logger.error("WebSocket error for build %s: %s", build_id, e)
    finally:
        event_bus.unsubscribe(build_id, queue)
