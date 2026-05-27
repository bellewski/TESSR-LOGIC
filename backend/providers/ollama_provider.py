import httpx
import json
import logging
from backend.providers.base import BaseModelProvider, ModelRequest, ModelResponse
from backend.config import settings

logger = logging.getLogger(__name__)


class OllamaProvider(BaseModelProvider):
    def __init__(self, base_url: str | None = None, fast_model: str | None = None,
                 quality_model: str | None = None, timeout: int | None = None, mode: str = "fast"):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.fast_model = fast_model or settings.ollama_fast_model
        self.quality_model = quality_model or settings.ollama_quality_model
        self.timeout = timeout or settings.ollama_timeout
        self.mode = mode

    @property
    def model(self) -> str:
        return self.quality_model if self.mode == "quality" else self.fast_model

    async def complete(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

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
            logger.error("Ollama request timed out after %s seconds", self.timeout)
            return ModelResponse(content="", model=self.model, success=False, error="Request timed out")
        except httpx.HTTPStatusError as e:
            logger.error("Ollama HTTP error: %s", e)
            return ModelResponse(content="", model=self.model, success=False, error=str(e))
        except Exception as e:
            logger.error("Ollama unexpected error: %s", e)
            return ModelResponse(content="", model=self.model, success=False, error=str(e))

    async def stream_complete(self, request: ModelRequest):
        """Streams the LLM response chunk by chunk."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": request.prompt,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    await response.aread()
                    raise Exception(f"Ollama Error: {response.text}")

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            raise Exception(data["error"])
                        if "response" in data:
                            yield data["response"]
                    except json.JSONDecodeError:
                        continue

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
