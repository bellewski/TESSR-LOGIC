from sqlalchemy.orm import Session
from backend.repositories.settings_repo import SettingsRepository
from backend.config import settings
from backend.schemas.settings import SettingsRead, SettingsUpdate

SETTINGS_KEYS = ["ollama_base_url", "ollama_fast_model", "ollama_quality_model", "ollama_timeout", "workspace_path"]


class SettingsService:
    def __init__(self, db: Session):
        self.repo = SettingsRepository(db)

    def get_all(self) -> SettingsRead:
        stored = self.repo.get_all()
        return SettingsRead(
            ollama_base_url=stored.get("ollama_base_url", settings.ollama_base_url),
            ollama_fast_model=stored.get("ollama_fast_model", settings.ollama_fast_model),
            ollama_quality_model=stored.get("ollama_quality_model", settings.ollama_quality_model),
            ollama_timeout=int(stored.get("ollama_timeout", settings.ollama_timeout)),
            workspace_path=stored.get("workspace_path", settings.workspace_path),
        )

    def update(self, updates: SettingsUpdate) -> SettingsRead:
        for key in SETTINGS_KEYS:
            val = getattr(updates, key, None)
            if val is not None:
                self.repo.set(key, str(val))
        return self.get_all()
