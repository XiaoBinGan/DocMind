"""LLM service — unified OpenAI-compatible client for all providers.

All providers (OpenAI, Anthropic, Ollama, and any OpenAI-compatible endpoint)
are accessed through the ``openai`` AsyncOpenAI SDK by pointing ``base_url``
at the appropriate server.  This eliminates provider-specific code paths and
makes it trivial to add new backends.

Configuration is read from the ``settings`` DB table at call time so that
changes made via the Settings UI take effect immediately.
"""
from __future__ import annotations

import re
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

# Default per-provider mapping
_PROVIDER_DEFAULTS: dict[str, dict] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-haiku-20240307",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
    },
    "openai_compatible": {
        "base_url": "",
        "model": "",
    },
}


def _filter_think_tokens(text: str) -> str:
    """Remove <think/></think/ thinks...  artifacts and zero-width spaces."""
    text = re.sub(r"<think[^>]*>.*?</think\s*>", "", text, flags=re.DOTALL)
    text = text.replace("\u200b", "")
    return text.strip()


class LLMService:
    """Stateless facade — config is fetched from DB on every call."""

    # -- public API -------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        stream: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Yield response chunks (or the full string when *stream* is False)."""
        client, model = await self._build_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            temperature=0.7,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        self._last_model = model
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0
        self._last_total_tokens = 0

        if stream:
            async for chunk in resp:
                if hasattr(chunk, 'usage') and chunk.usage:
                    self._last_prompt_tokens = chunk.usage.prompt_tokens or self._last_prompt_tokens
                    self._last_completion_tokens = chunk.usage.completion_tokens or self._last_completion_tokens
                    self._last_total_tokens = chunk.usage.total_tokens or self._last_total_tokens
                delta = chunk.choices[0].delta.content
                if delta:
                    cleaned = _filter_think_tokens(delta)
                    if cleaned:
                        yield cleaned
        else:
            if resp.usage:
                self._last_prompt_tokens = resp.usage.prompt_tokens or 0
                self._last_completion_tokens = resp.usage.completion_tokens or 0
                self._last_total_tokens = resp.usage.total_tokens or 0
            text = resp.choices[0].message.content or ""
            cleaned = _filter_think_tokens(text)
            if cleaned:
                yield cleaned

    @property
    def last_usage(self):
        """Return (prompt_tokens, completion_tokens, total_tokens) from last generate call."""
        return (self._last_prompt_tokens, self._last_completion_tokens, self._last_total_tokens)

    async def generate_structure(self, prompt: str) -> str:
        """Non-streaming structured output (used by indexer)."""
        system = (
            "You are a document analysis expert. "
            "Always respond with valid JSON in the specified format. "
            "Do not include any other text."
        )
        parts: list[str] = []
        async for chunk in self.generate(system, prompt, stream=False):
            parts.append(chunk)
        return "".join(parts).strip()

    async def test_connection(self) -> tuple[bool, str]:
        """Quick connectivity test. Returns (ok, message)."""
        try:
            client, model = await self._build_client()
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            return True, f"Connected — model: {model}"
        except Exception as exc:
            return False, str(exc)

    # -- internal ---------------------------------------------------------

    async def _build_client(self) -> tuple[AsyncOpenAI, str]:
        provider = await settings_service.llm_provider()
        api_key = await settings_service.llm_api_key()
        base_url = await settings_service.llm_base_url()
        model = await settings_service.llm_model()

        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        effective_base = base_url or defaults.get("base_url", "")
        effective_model = model or defaults.get("model", "")

        # Ollama doesn't need a real key
        if not api_key and provider == "ollama":
            api_key = "not-needed"

        if not effective_base or not effective_model:
            raise RuntimeError(
                f"Missing configuration for provider '{provider}'. "
                "Please set Base URL and Model in Settings."
            )

        client = AsyncOpenAI(base_url=effective_base, api_key=api_key)
        return client, effective_model


# Global singleton
llm_service = LLMService()
