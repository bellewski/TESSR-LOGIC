from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BuildEventRead(BaseModel):
    id: str
    build_id: str
    phase: Optional[str]
    event_type: str
    message: str
    payload: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class BuildEventList(BaseModel):
    events: list[BuildEventRead]
    total: int
