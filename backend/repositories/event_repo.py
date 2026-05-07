from sqlalchemy.orm import Session
from typing import Optional
from backend.models.event import BuildEvent


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, build_id: str, event_type: str, message: str, phase: Optional[str] = None, payload: Optional[str] = None) -> BuildEvent:
        event = BuildEvent(
            build_id=build_id,
            event_type=event_type,
            message=message,
            phase=phase,
            payload=payload,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_by_build(self, build_id: str, skip: int = 0, limit: int = 200) -> tuple[list[BuildEvent], int]:
        total = self.db.query(BuildEvent).filter(BuildEvent.build_id == build_id).count()
        events = (
            self.db.query(BuildEvent)
            .filter(BuildEvent.build_id == build_id)
            .order_by(BuildEvent.created_at)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return events, total
