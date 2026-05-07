from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
from backend.models.build_directory import BuildDirectoryConfig


class DirectoryConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, build_id: str, source_dir: Optional[str] = None,
               workspace_dir: Optional[str] = None, output_dir: Optional[str] = None,
               project_context_id: Optional[str] = None,
               prompt_template_id: Optional[str] = None) -> BuildDirectoryConfig:
        cfg = BuildDirectoryConfig(
            build_id=build_id,
            source_dir=source_dir,
            workspace_dir=workspace_dir,
            output_dir=output_dir,
            project_context_id=project_context_id,
            prompt_template_id=prompt_template_id,
        )
        self.db.add(cfg)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg

    def get_by_build(self, build_id: str) -> Optional[BuildDirectoryConfig]:
        return self.db.query(BuildDirectoryConfig).filter(BuildDirectoryConfig.build_id == build_id).first()

    def update_output(self, build_id: str, final_output_path: str, files_written: int) -> Optional[BuildDirectoryConfig]:
        cfg = self.get_by_build(build_id)
        if not cfg:
            return None
        cfg.final_output_path = final_output_path
        cfg.files_written = files_written
        cfg.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg
