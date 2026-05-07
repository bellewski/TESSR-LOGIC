from sqlalchemy.orm import Session
from typing import Optional
from backend.models.finding import Finding


class FindingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, build_id: str, severity: str, category: str, description: str,
               file_path: Optional[str] = None, line_number: Optional[int] = None,
               remediation: Optional[str] = None) -> Finding:
        finding = Finding(
            build_id=build_id,
            severity=severity,
            category=category,
            description=description,
            file_path=file_path,
            line_number=line_number,
            remediation=remediation,
        )
        self.db.add(finding)
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def list_by_build(self, build_id: str) -> tuple[list[Finding], int]:
        findings = self.db.query(Finding).filter(Finding.build_id == build_id).all()
        return findings, len(findings)
