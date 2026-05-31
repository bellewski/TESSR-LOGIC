import httpx
import logging
from backend.providers.base import BaseModelProvider, ModelRequest, ModelResponse
from backend.config import settings

logger = logging.getLogger(__name__)


def _get_live_settings():
    """Read settings from DB so UI changes take effect without restart."""
    try:
        from backend.database import SessionLocal
        from backend.repositories.settings_repo import SettingsRepository
        db = SessionLocal()
        try:
            repo = SettingsRepository(db)
            stored = repo.get_all()
            return stored
        finally:
            db.close()
    except Exception:
        return {}


def get_model_for_agent(agent_type: str) -> str:
    """Return the best model for a given agent type, reading live from DB."""
    live = _get_live_settings()

    # Per-agent overrides from config env (highest priority)
    env_overrides = {
        "architect":       settings.ollama_architect_model,
        "coder":           settings.ollama_coder_model,
        "ui_designer":     settings.ollama_ui_designer_model,
        "hardener":        settings.ollama_hardener_model,
        "fixer":           settings.ollama_fixer_model,
        "validator":       settings.ollama_validator_model,
        "project_manager": settings.ollama_project_manager_model,
    }
    override = env_overrides.get(agent_type, "")
    if override:
        return override

    # Read from DB (set via Settings page)
    fast_model     = live.get("ollama_fast_model")     or settings.ollama_fast_model
    creative_model = live.get("ollama_creative_model") or settings.ollama_creative_model

    creative_agents = {"architect", "ui_designer", "validator", "project_manager"}
    code_agents     = {"coder", "hardener", "fixer"}

    if agent_type in creative_agents:
        return creative_model
    elif agent_type in code_agents:
        return fast_model
    return fast_model


class OllamaProvider(BaseModelProvider):
    def __init__(self, base_url: str | None = None, fast_model: str | None = None,
                 quality_model: str | None = None, creative_model: str | None = None,
                 timeout: int | None = None, mode: str = "fast", agent_type: str = ""):
        live = _get_live_settings()
        self.base_url      = (base_url or live.get("ollama_base_url") or settings.ollama_base_url).rstrip("/")
        self.fast_model    = fast_model    or live.get("ollama_fast_model")     or settings.ollama_fast_model
        self.quality_model = quality_model or live.get("ollama_quality_model")  or settings.ollama_quality_model
        self.creative_model= creative_model or live.get("ollama_creative_model") or settings.ollama_creative_model
        self.timeout       = timeout or int(live.get("ollama_timeout") or settings.ollama_timeout)
        self.mode          = mode
        self.agent_type    = agent_type

    @property
    def model(self) -> str:
        if self.agent_type:
            return get_model_for_agent(self.agent_type)
        if self.mode == "quality":
            return self.quality_model
        elif self.mode == "creative":
            return self.creative_model
        return self.fast_model

    async def stream_complete(self, request: ModelRequest):
        """Stream not supported — falls back to complete()."""
        response = await self.complete(request)
        yield response

    async def complete(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/api/generate"
        # Bound generation so a single file can't run for many minutes, and set an
        # explicit context window so prompt+output fit coherently. Default Ollama
        # context is only 4096; combined with an unbounded num_predict this made
        # each file crawl (and spill to CPU on small GPUs). These keep it fast and
        # on-GPU for 7-8B coder models on ~10GB cards. Tunable via DB settings.
        live = _get_live_settings()
        num_ctx = int(live.get("ollama_num_ctx") or 8192)
        max_predict = int(live.get("ollama_num_predict") or 6144)
        num_predict = min(request.max_tokens or max_predict, max_predict)
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        logger.info("Ollama [%s] → %s (temp=%.2f, max_tokens=%d)",
                    self.agent_type or self.mode, self.model,
                    request.temperature, request.max_tokens)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return ModelResponse(
                    content=data.get("response", ""),
                    model=self.model,
                    prompt_tokens=data.get("prompt_eval_count", 0),
                    completion_tokens=data.get("eval_count", 0),
                    success=True,
                )
        except httpx.TimeoutException:
            logger.error("Ollama [%s] timed out after %ss", self.agent_type, self.timeout)
            return ModelResponse(content="", model=self.model, success=False, error="Request timed out")
        except httpx.HTTPStatusError as e:
            body = ""
            try: body = e.response.text
            except: pass
            logger.error("Ollama HTTP error [%s]: %s %s", self.agent_type, e, body)
            return ModelResponse(content="", model=self.model, success=False,
                                 error=f"Ollama Error: {body or str(e)}")
        except Exception as e:
            logger.error("Ollama unexpected error [%s]: %s", self.agent_type, e)
            return ModelResponse(content="", model=self.model, success=False, error=str(e))

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
