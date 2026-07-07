import logging
import os
from backend.database import SessionLocal
from backend.repositories.agent_config_repo import AgentConfigRepository

logger = logging.getLogger(__name__)


def load_system_prompt(agent_type: str, default: str) -> str:
    """Return the agent's system prompt.

    CODE DEFAULTS ARE AUTHORITATIVE. Shipped prompt improvements must take
    effect on update — previously, prompts stored in the DB silently
    overrode every shipped fix, making prompt updates inert.

    To use DB-stored prompts (Prompt Studio customization), opt in with
    the environment variable TESSR_USE_DB_PROMPTS=1.
    """
    if os.getenv("TESSR_USE_DB_PROMPTS", "").lower() not in ("1", "true", "yes"):
        return default
    try:
        db = SessionLocal()
        try:
            repo = AgentConfigRepository(db)
            cfg = repo.get_by_type(agent_type)
            if cfg and cfg.system_prompt:
                logger.info("Using DB-stored prompt for %s (TESSR_USE_DB_PROMPTS=1)", agent_type)
                return cfg.system_prompt
        finally:
            db.close()
    except Exception as e:
        logger.warning("Could not load system prompt for %s from DB: %s", agent_type, e)
    return default
