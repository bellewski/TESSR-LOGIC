from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    ollama_base_url: str = "http://localhost:11434"

    # Per-role model assignment — each agent uses the model best suited for its job
    ollama_fast_model: str = "qwen2.5-coder:7b"      # Coder, Hardener, Fixer
    ollama_quality_model: str = "codellama:13b"        # Fallback quality
    ollama_creative_model: str = "llama3.1:8b"         # Architect, UI Designer, Validator, PM

    # Per-agent overrides (if set, used instead of role defaults)
    ollama_architect_model: str = ""
    ollama_coder_model: str = ""
    ollama_ui_designer_model: str = ""
    ollama_hardener_model: str = ""
    ollama_fixer_model: str = ""
    ollama_validator_model: str = ""
    ollama_project_manager_model: str = ""

    ollama_timeout: int = 180
    workspace_path: str = "workspace/builds"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
