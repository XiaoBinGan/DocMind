"""Settings API — CRUD for the settings table + test-connection helper."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.settings_service import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------- schemas -------------------------------------------------------

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class SettingsResponse(BaseModel):
    settings: Dict[str, str]


class TestResponse(BaseModel):
    success: bool
    message: str


class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str
    defaults: Dict[str, str]
    fields: list[str]  # which keys the user needs to fill


# ---------- routes --------------------------------------------------------

@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Return all settings.  API keys are partially masked."""
    all_settings = await settings_service.get_all()
    masked: Dict[str, str] = {}
    for k, v in all_settings.items():
        if k.endswith("api_key") and v and len(v) > 8:
            masked[k] = v[:3] + "***" + v[-4:]
        else:
            masked[k] = v
    return SettingsResponse(settings=masked)


@router.put("", response_model=SettingsResponse)
async def update_settings(body: SettingsUpdateRequest):
    """Batch-update settings.  API keys sent as \"***...\" are kept unchanged."""
    existing = await settings_service.get_all()
    to_save: Dict[str, Any] = {}
    for k, v in body.settings.items():
        # If the value looks masked, keep the existing real value
        if isinstance(v, str) and "***" in v and k in existing:
            to_save[k] = existing[k]
        else:
            to_save[k] = v
    result = await settings_service.save_all(to_save)
    return SettingsResponse(settings=result)


@router.post("/test", response_model=TestResponse)
async def test_connection():
    """Test the current LLM configuration."""
    from app.services.llm import llm_service
    ok, msg = await llm_service.test_connection()
    return TestResponse(success=ok, message=msg)


@router.get("/providers")
async def list_providers():
    """Return supported providers with their default config."""
    providers = [
        ProviderInfo(
            id="openai",
            name="OpenAI",
            description="OpenAI 官方 API（GPT-4o, GPT-4o-mini 等）",
            defaults={"llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o-mini"},
            fields=["llm_api_key", "llm_model"],
        ),
        ProviderInfo(
            id="anthropic",
            name="Anthropic",
            description="Anthropic 官方 API（Claude 系列）",
            defaults={"llm_base_url": "https://api.anthropic.com/v1", "llm_model": "claude-3-haiku-20240307"},
            fields=["llm_api_key", "llm_model"],
        ),
        ProviderInfo(
            id="ollama",
            name="Ollama (本地)",
            description="本地 Ollama 服务",
            defaults={"llm_base_url": "http://localhost:11434/v1", "llm_model": "llama3"},
            fields=["llm_base_url", "llm_model"],
        ),
        ProviderInfo(
            id="openai_compatible",
            name="OpenAI 兼容",
            description="任意兼容 OpenAI API 的服务（DeepSeek、智谱、Moonshot、通义千问等）",
            defaults={"llm_base_url": "", "llm_model": ""},
            fields=["llm_base_url", "llm_api_key", "llm_model"],
        ),
    ]
    return {"providers": [p.model_dump() for p in providers]}
