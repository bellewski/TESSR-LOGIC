import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base
import enum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BuildStatus(str, enum.Enum):
    created = "created"
    queued = "queued"
    running = "running"
    failed = "failed"
    completed = "completed"


class BuildPhase(str, enum.Enum):
    architecting = "architecting"
    coding = "coding"
    designing = "designing"
    hardening = "hardening"
    fixing = "fixing"
    validating = "validating"
    building = "building"
    testing = "testing"


class BuildMode(str, enum.Enum):
    fast = "fast"
    quality = "quality"


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    stack_target: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(SAEnum(BuildMode), nullable=False, default=BuildMode.fast)
    status: Mapped[str] = mapped_column(SAEnum(BuildStatus), nullable=False, default=BuildStatus.created)
    current_phase: Mapped[str | None] = mapped_column(SAEnum(BuildPhase), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
