import logging
from backend.database import SessionLocal
from backend.repositories.agent_config_repo import AgentConfigRepository

logger = logging.getLogger(__name__)


def load_system_prompt(agent_type: str, default: str) -> str:
    """Load an agent's system prompt from DB config, falling back to hardcoded default."""
    try:
        db = SessionLocal()
        try:
            repo = AgentConfigRepository(db)
            cfg = repo.get_by_type(agent_type)
            if cfg and cfg.system_prompt:
                return cfg.system_prompt
        finally:
            db.close()
    except Exception as e:
        logger.warning("Could not load system prompt for %s from DB: %s", agent_type, e)
    return default
