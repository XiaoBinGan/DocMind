from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models():
    """List available LLM models based on provider configuration."""
    from app.services.settings_service import settings_service
    from app.services.llm import llm_service

    provider = await settings_service.llm_provider()
    base_url = await settings_service.llm_base_url()
    model = await settings_service.llm_model()

    # For Ollama / OpenAI-compatible, try to fetch models from the server
    if provider in ("ollama", "openai_compatible"):
        try:
            api_key = await settings_service.llm_api_key()
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key or "not-needed",
            )
            models_resp = await client.models.list()
            names = sorted([m.id for m in models_resp.data])
            return {
                "provider": provider,
                "models": names,
                "base_url": base_url,
                "current": model,
            }
        except Exception as e:
            return {
                "provider": provider,
                "models": [],
                "base_url": base_url,
                "current": model,
                "error": str(e),
            }

    # For OpenAI / Anthropic, return configured models
    if provider == "openai":
        return {
            "provider": provider,
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "current": model,
        }
    elif provider == "anthropic":
        return {
            "provider": provider,
            "models": [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307",
            ],
            "current": model,
        }

    return {"provider": provider, "models": [], "current": model}
