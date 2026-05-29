from pydantic import BaseModel
from typing import Optional


class SettingsRead(BaseModel):
    ollama_base_url: str
    ollama_fast_model: str
    ollama_quality_model: str
    ollama_creative_model: str = "llama3.1:8b"
    ollama_timeout: int
    workspace_path: str


class SettingsUpdate(BaseModel):
    ollama_base_url: Optional[str] = None
    ollama_fast_model: Optional[str] = None
    ollama_quality_model: Optional[str] = None
    ollama_creative_model: Optional[str] = None
    ollama_timeout: Optional[int] = None
    workspace_path: Optional[str] = None
