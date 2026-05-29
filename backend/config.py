from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "TESSR-LOGIC"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    database_url: str = "sqlite:///./tessr_logic.db"

    # Workspace
    workspace_path: str = "workspace/builds"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Per-role model assignment
    ollama_fast_model: str = "deepseek-coder:33b"     # Coder, Hardener, Fixer
    ollama_quality_model: str = "codellama:13b"        # Fallback quality
    ollama_creative_model: str = "llama3.1:8b"         # Architect, UI Designer, Validator, PM

    # Per-agent overrides (leave empty to use role defaults above)
    ollama_architect_model: str = ""
    ollama_coder_model: str = ""
    ollama_ui_designer_model: str = ""
    ollama_hardener_model: str = ""
    ollama_fixer_model: str = ""
    ollama_validator_model: str = ""
    ollama_project_manager_model: str = ""

    ollama_timeout: int = 180

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
