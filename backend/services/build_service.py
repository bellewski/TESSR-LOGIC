from typing import Optional
from sqlalchemy.orm import Session
from backend.repositories.build_repo import BuildRepository
from backend.repositories.event_repo import EventRepository
from backend.repositories.file_repo import FileRepository
from backend.repositories.finding_repo import FindingRepository
from backend.repositories.directory_repo import DirectoryConfigRepository
from backend.models.build import BuildStatus
from backend.orchestrator.job_queue import job_queue
import logging

logger = logging.getLogger(__name__)


class BuildService:
    def __init__(self, db: Session):
        self.db = db
        self.build_repo = BuildRepository(db)
        self.event_repo = EventRepository(db)
        self.file_repo = FileRepository(db)
        self.finding_repo = FindingRepository(db)
        self.dir_repo = DirectoryConfigRepository(db)

    async def create_and_enqueue(
        self, project_name: str, requirement: str, stack_target: str, mode: str,
        project_context_id: Optional[str] = None, prompt_template_id: Optional[str] = None,
        source_dir: Optional[str] = None, workspace_dir: Optional[str] = None, output_dir: Optional[str] = None,
    ):
        build = self.build_repo.create(project_name, requirement, stack_target, mode)
        self.build_repo.update_status(build.id, BuildStatus.queued)

        # Persist directory config
        self.dir_repo.create(
            build_id=build.id,
            source_dir=source_dir,
            workspace_dir=workspace_dir,
            output_dir=output_dir,
            project_context_id=project_context_id,
            prompt_template_id=prompt_template_id,
        )

        self.event_repo.create(
            build_id=build.id,
            event_type="build_created",
            message=f"Build '{project_name}' created and queued",
        )
        await job_queue.enqueue(build.id)
        self.db.refresh(build)
        return build

    def get_build(self, build_id: str):
        return self.build_repo.get_by_id(build_id)

    def list_builds(self, skip: int = 0, limit: int = 50):
        return self.build_repo.list_all(skip, limit)

    def list_events(self, build_id: str, skip: int = 0, limit: int = 200):
        return self.event_repo.list_by_build(build_id, skip, limit)

    def list_files(self, build_id: str):
        return self.file_repo.list_by_build(build_id)

    def list_findings(self, build_id: str):
        return self.finding_repo.list_by_build(build_id)

    def get_directory_config(self, build_id: str):
        return self.dir_repo.get_by_build(build_id)

    def cancel_build(self, build_id: str):
        return self.build_repo.cancel(build_id)
