from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ProjectContextCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_dir: Optional[str] = None
    workspace_dir: Optional[str] = None
    output_dir: Optional[str] = None


class ProjectContextUpdate(BaseModel):
    name: Optional[str] = None
    source_dir: Optional[str] = None
    workspace_dir: Optional[str] = None
    output_dir: Optional[str] = None


class FileManifestEntryRead(BaseModel):
    id: str
    context_id: str
    relative_path: str
    file_name: str
    extension: Optional[str]
    size_bytes: int
    is_key_file: bool
    detected_language: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectContextRead(BaseModel):
    id: str
    name: str
    source_dir: Optional[str]
    workspace_dir: Optional[str]
    output_dir: Optional[str]
    detected_stack: Optional[str]
    detected_files: Optional[str]
    inferred_project_type: Optional[str]
    context_summary: Optional[str]
    context_summary_json: Optional[str]
    total_files_scanned: int
    last_scanned_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanRequest(BaseModel):
    source_dir: str
    context_id: Optional[str] = None


class ScanResult(BaseModel):
    context_id: str
    detected_stack: list[str]
    inferred_project_type: str
    total_files: int
    key_files: list[str]
    ignored_folders: list[str]
    context_summary: str
    context_summary_json: dict


class BuildDirectoryConfigRead(BaseModel):
    id: str
    build_id: str
    source_dir: Optional[str]
    workspace_dir: Optional[str]
    output_dir: Optional[str]
    project_context_id: Optional[str]
    prompt_template_id: Optional[str]
    final_output_path: Optional[str]
    files_written: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
