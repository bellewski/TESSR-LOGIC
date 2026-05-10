from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "TESSR-LOGIC"
    debug: bool = False

    database_url: str = "sqlite:///./tessr_logic.db"

    ollama_base_url: str = "http://localhost:11434"
    ollama_fast_model: str = "qwen2.5-coder:7b"
    ollama_quality_model: str = "qwen2.5-coder:7b"
    ollama_timeout: int = 120

    workspace_path: str = str(Path.cwd() / "workspace" / "builds")

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
