"""Settings service — reads/writes LLM config from the settings DB table."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.database import Setting

logger = logging.getLogger(__name__)

# Well-known keys
KEY_PROVIDER = "llm_provider"
KEY_API_KEY = "llm_api_key"
KEY_BASE_URL = "llm_base_url"
KEY_MODEL = "llm_model"


class SettingsService:
    """Thin async wrapper around the settings table.

    Call ``init(session_maker)`` once after the DB engine is ready.
    """

    def __init__(self) -> None:
        self._sm: Optional[async_sessionmaker] = None
        # In-memory cache — populated on first load / reload
        self._cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def init(self, session_maker: async_sessionmaker) -> None:
        self._sm = session_maker

    @property
    def ready(self) -> bool:
        return self._sm is not None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in self._cache:
            return self._cache[key]
        val = await self._db_get(key)
        if val is not None:
            self._cache[key] = val
        return val if val is not None else default

    async def set(self, key: str, value: str) -> None:
        self._cache[key] = value
        await self._db_upsert(key, value)

    async def get_all(self) -> Dict[str, str]:
        rows = await self._db_get_all()
        self._cache = {r.key: r.value for r in rows if r.value is not None}
        return dict(self._cache)

    async def save_all(self, data: Dict[str, Any]) -> Dict[str, str]:
        for k, v in data.items():
            sv = str(v) if v is not None else ""
            self._cache[k] = sv
        await self._db_upsert_many(self._cache)
        return dict(self._cache)

    async def reload(self) -> None:
        """Re-read everything from DB (invalidates cache)."""
        await self.get_all()

    # ------------------------------------------------------------------
    # LLM-specific convenience
    # ------------------------------------------------------------------
    async def llm_provider(self) -> str:
        return await self.get(KEY_PROVIDER, "ollama")

    async def llm_api_key(self) -> str:
        return await self.get(KEY_API_KEY, "")

    async def llm_base_url(self) -> str:
        return await self.get(KEY_BASE_URL, "http://localhost:11434/v1")

    async def llm_model(self) -> str:
        return await self.get(KEY_MODEL, "llama3")

    # ------------------------------------------------------------------
    # Internal DB access
    # ------------------------------------------------------------------
    async def _db_get(self, key: str) -> Optional[str]:
        if not self._sm:
            return None
        async with self._sm() as session:
            row = await session.get(Setting, key)
            return row.value if row else None

    async def _db_get_all(self):
        if not self._sm:
            return []
        async with self._sm() as session:
            result = await session.execute(select(Setting))
            return result.scalars().all()

    async def _db_upsert(self, key: str, value: str) -> None:
        if not self._sm:
            return
        async with self._sm() as session:
            row = await session.get(Setting, key)
            if row:
                row.value = value
            else:
                session.add(Setting(key=key, value=value))
            await session.commit()

    async def _db_upsert_many(self, data: Dict[str, str]) -> None:
        if not self._sm:
            return
        async with self._sm() as session:
            for key, value in data.items():
                row = await session.get(Setting, key)
                if row:
                    row.value = value
                else:
                    session.add(Setting(key=key, value=value))
            await session.commit()


# Global singleton
settings_service = SettingsService()
