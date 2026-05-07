import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class BuildDirectoryConfig(Base):
    """Per-build directory configuration - source, workspace, and output paths."""
    __tablename__ = "build_directory_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    build_id: Mapped[str] = mapped_column(String(36), ForeignKey("builds.id"), nullable=False, unique=True, index=True)

    source_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional: which project context was used
    project_context_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prompt_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Populated on pipeline completion
    final_output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_written: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
