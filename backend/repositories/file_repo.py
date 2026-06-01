from sqlalchemy.orm import Session
from backend.models.file_record import GeneratedFile


class FileRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, build_id: str, file_path: str, file_name: str, phase: str, size_bytes: int = 0, content_preview: str = "") -> GeneratedFile:
        # Upsert by (build_id, file_path): when a later phase (e.g. UI Designer)
        # rewrites a file the Coder already produced, update the existing row instead
        # of inserting a duplicate — so the Files list shows each file ONCE.
        rec = (
            self.db.query(GeneratedFile)
            .filter(GeneratedFile.build_id == build_id, GeneratedFile.file_path == file_path)
            .first()
        )
        if rec:
            rec.file_name = file_name
            rec.phase = phase
            rec.size_bytes = size_bytes
            rec.content_preview = content_preview[:2000] if content_preview else ""
        else:
            rec = GeneratedFile(
                build_id=build_id,
                file_path=file_path,
                file_name=file_name,
                phase=phase,
                size_bytes=size_bytes,
                content_preview=content_preview[:2000] if content_preview else "",
            )
            self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def list_by_build(self, build_id: str) -> tuple[list[GeneratedFile], int]:
        records = self.db.query(GeneratedFile).filter(GeneratedFile.build_id == build_id).all()
        return records, len(records)

    def clear_by_build(self, build_id: str) -> int:
        """Clear all generated files for a build - used for clean round restarts"""
        count = self.db.query(GeneratedFile).filter(GeneratedFile.build_id == build_id).count()
        self.db.query(GeneratedFile).filter(GeneratedFile.build_id == build_id).delete()
        self.db.commit()
        return count
