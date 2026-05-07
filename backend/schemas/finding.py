from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FindingRead(BaseModel):
    id: str
    build_id: str
    severity: str
    category: str
    file_path: Optional[str]
    line_number: Optional[int]
    description: str
    remediation: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingList(BaseModel):
    findings: list[FindingRead]
    total: int
