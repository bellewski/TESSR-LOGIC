from fastapi import APIRouter
from backend.providers.ollama_provider import OllamaProvider

router = APIRouter(prefix="/ollama", tags=["ollama"])


@router.get("/health")
async def ollama_health():
    provider = OllamaProvider()
    ok = await provider.health_check()
    return {"status": "ok" if ok else "unreachable", "connected": ok}


@router.get("/models")
async def list_ollama_models():
    provider = OllamaProvider()
    models = await provider.list_models()
    return {"models": models}
