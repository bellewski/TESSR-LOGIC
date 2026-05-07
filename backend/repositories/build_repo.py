from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime, timezone
from backend.models.build import Build, BuildStatus, BuildPhase


class BuildRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, project_name: str, requirement: str, stack_target: str, mode: str) -> Build:
        build = Build(
            project_name=project_name,
            requirement=requirement,
            stack_target=stack_target,
            mode=mode,
        )
        self.db.add(build)
        self.db.commit()
        self.db.refresh(build)
        return build

    def get_by_id(self, build_id: str) -> Optional[Build]:
        return self.db.query(Build).filter(Build.id == build_id).first()

    def list_all(self, skip: int = 0, limit: int = 50) -> tuple[list[Build], int]:
        total = self.db.query(Build).count()
        builds = self.db.query(Build).order_by(desc(Build.created_at)).offset(skip).limit(limit).all()
        return builds, total

    def update_status(self, build_id: str, status: BuildStatus, phase: Optional[BuildPhase] = None, error: Optional[str] = None) -> Optional[Build]:
        build = self.get_by_id(build_id)
        if not build:
            return None
        # Guard: never overwrite a terminal (failed/completed) status — prevents cancel race conditions
        if str(build.status) in (str(BuildStatus.failed), str(BuildStatus.completed)):
            return build
        build.status = status
        if phase is not None:
            build.current_phase = phase
        if error is not None:
            build.error_message = error
        if status in (BuildStatus.completed, BuildStatus.failed):
            build.completed_at = datetime.now(timezone.utc)
        build.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(build)
        return build

    def cancel(self, build_id: str) -> Optional[Build]:
        build = self.get_by_id(build_id)
        if not build:
            return None
        build.status = BuildStatus.failed
        build.error_message = "Cancelled by user"
        build.updated_at = datetime.now(timezone.utc)
        build.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(build)
        return build

    def increment_retry(self, build_id: str) -> Optional[Build]:
        build = self.get_by_id(build_id)
        if not build:
            return None
        build.retry_count += 1
        build.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(build)
        return build
