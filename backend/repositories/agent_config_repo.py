import logging
from typing import Sequence
from sqlalchemy.orm import Session
from backend.models.agent_config import AgentConfig, BUILTIN_AGENTS

logger = logging.getLogger(__name__)


class AgentConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def seed_builtin(self):
        """Create builtin agent config rows if they don't exist."""
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
