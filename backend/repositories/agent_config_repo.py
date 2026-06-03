import logging
from typing import Sequence
from sqlalchemy.orm import Session
from backend.models.agent_config import AgentConfig, BUILTIN_AGENTS

logger = logging.getLogger(__name__)


class AgentConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_schema(self):
        """Lightweight migration: add columns introduced after the table was first created
        (SQLite has no auto-migration). Safe + idempotent."""
        from sqlalchemy import text
        try:
            cols = {r[1] for r in self.db.execute(text("PRAGMA table_info(agent_configs)")).fetchall()}
            if "can_edit" not in cols:
                self.db.execute(text("ALTER TABLE agent_configs ADD COLUMN can_edit BOOLEAN NOT NULL DEFAULT 0"))
                self.db.commit()
                logger.info("agent_configs: added can_edit column")
        except Exception as e:
            logger.warning("ensure_schema failed (non-fatal): %s", e)

    def seed_builtin(self):
        """Create builtin agent config rows if they don't exist."""
        self.ensure_schema()
        for cfg in BUILTIN_AGENTS:
            existing = self.db.query(AgentConfig).filter(AgentConfig.name == cfg["name"]).first()
            if existing is None:
                self.db.add(AgentConfig(**cfg))
        self.db.commit()

    def list_all(self) -> Sequence[AgentConfig]:
        return self.db.query(AgentConfig).order_by(AgentConfig.position.asc()).all()

    def get_by_id(self, agent_id: str) -> AgentConfig | None:
        return self.db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()

    def get_by_type(self, agent_type: str) -> AgentConfig | None:
        return self.db.query(AgentConfig).filter(AgentConfig.agent_type == agent_type).first()

    def create(self, data: dict) -> AgentConfig:
        agent = AgentConfig(**data)
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update(self, agent_id: str, data: dict) -> AgentConfig | None:
        agent = self.get_by_id(agent_id)
        if not agent:
            return None
        for key, value in data.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def delete(self, agent_id: str) -> bool:
        agent = self.get_by_id(agent_id)
        if not agent:
            return False
        if agent.is_builtin:
            logger.warning("Cannot delete builtin agent %s", agent.name)
            return False
        self.db.delete(agent)
        self.db.commit()
        return True

    def get_enabled_pipeline(self) -> Sequence[AgentConfig]:
        return (
            self.db.query(AgentConfig)
            .filter(AgentConfig.enabled == True)
            .order_by(AgentConfig.position.asc())
            .all()
        )
