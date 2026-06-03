from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from backend.models.build import BuildStatus, BuildPhase, BuildMode


class BuildCreate(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255)
    requirement: str = Field(..., min_length=10)
    stack_target: str = Field(default="auto", max_length=255)
    mode: BuildMode = BuildMode.fast
    # Optional context/directory linkage
    project_context_id: Optional[str] = None
    prompt_template_id: Optional[str] = None
    source_dir: Optional[str] = None
    workspace_dir: Optional[str] = None
    output_dir: Optional[str] = None
    brand_kit: Optional[str] = None  # slug under assets/brand-kits/ to apply to this build


class BuildRead(BaseModel):
    id: str
    project_name: str
    requirement: str
    stack_target: str
    mode: BuildMode
    status: BuildStatus
    current_phase: Optional[BuildPhase]
    retry_count: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BuildList(BaseModel):
    builds: list[BuildRead]
    total: int
