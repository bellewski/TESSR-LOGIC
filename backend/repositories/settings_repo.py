from sqlalchemy.orm import Session
from backend.models.app_settings import AppSettings


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str) -> str | None:
        row = self.db.query(AppSettings).filter(AppSettings.key == key).first()
        return row.value if row else None

    def set(self, key: str, value: str) -> AppSettings:
        row = self.db.query(AppSettings).filter(AppSettings.key == key).first()
        if row:
            row.value = value
        else:
            row = AppSettings(key=key, value=value)
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_all(self) -> dict[str, str]:
        rows = self.db.query(AppSettings).all()
        return {r.key: r.value for r in rows}
