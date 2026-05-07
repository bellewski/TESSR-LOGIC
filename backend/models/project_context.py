import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class ProjectContext(Base):
    __tablename__ = "project_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    source_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scan results stored as JSON strings
    detected_stack: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON list
    detected_files: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON list of key files
    inferred_project_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)      # Human-readable summary
    context_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True) # Machine-readable JSON

    total_files_scanned: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class FileManifestEntry(Base):
    __tablename__ = "file_manifest_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    context_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    is_key_file: Mapped[bool] = mapped_column(default=False)
    detected_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
