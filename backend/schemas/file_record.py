from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class GeneratedFileRead(BaseModel):
    id: str
    build_id: str
    file_path: str
    file_name: str
    content_preview: Optional[str]
    size_bytes: int
    phase: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GeneratedFileList(BaseModel):
    files: list[GeneratedFileRead]
    total: int
