from abc import ABC, abstractmethod
from pydantic import BaseModel


class ModelRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    num_ctx: int | None = None                  # per-request context window override
    response_format: str | dict | None = None   # "json" or a JSON schema dict (Ollama structured output)


class ModelResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    success: bool = True
    error: str = ""


class BaseModelProvider(ABC):
    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        pass

    @abstractmethod
    async def stream_complete(self, request: ModelRequest):
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass
