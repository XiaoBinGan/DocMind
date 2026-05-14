"""Memory service — short-term and long-term memory management.

Inspired by OpenClaw's memory system:
- Daily notes (short-term): raw logs of conversations and decisions
- Long-term memory: curated, distilled insights
- Auto-extraction from conversations
- Semantic-like search via keyword matching
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.database import Memory
from app.services.llm import llm_service

logger = logging.getLogger(__name__)


# ---- CRUD ----

async def create_memory(
    user_id: str,
    content: str,
    category: str = "daily",
    source: str = "manual",
    source_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    importance: int = 5,
    db: Optional[AsyncSession] = None,
    session_maker: Optional[sessionmaker] = None,
) -> Memory:
    """Create a new memory entry."""
    if db is None and session_maker is not None:
        async with session_maker() as db:
            return await _do_create(db, user_id, content, category, source, source_id, tags, importance)
    if db is not None:
        return await _do_create(db, user_id, content, category, source, source_id, tags, importance)
    raise ValueError("Either db or session_maker must be provided")


async def _do_create(db, user_id, content, category, source, source_id, tags, importance) -> Memory:
    now = datetime.now(timezone.utc)
    mem = Memory(
        id=f"mem_{now.strftime('%Y%m%d%H%M%S')}_{user_id[:8]}",
        user_id=user_id,
        content=content,
        category=category,
        source=source,
        source_id=source_id,
        tags=json.dumps(tags or []),
        importance=importance,
        is_archived=0,
        created_at=now,
        updated_at=now,
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return mem


async def list_memories(
    user_id: str,
    category: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = None,
) -> tuple[list[Memory], int]:
    """List memories for a user, optionally filtered by category."""
    base = [Memory.user_id == user_id]
    if category:
        base.append(Memory.category == category)
    if not include_archived:
        base.append(Memory.is_archived == 0)

    count_q = select(func.count(Memory.id)).where(and_(*base))
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Memory)
        .where(and_(*base))
        .order_by(Memory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    return list(rows), total


async def get_memory(memory_id: str, user_id: str, db: AsyncSession) -> Optional[Memory]:
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_memory(
    memory_id: str,
    user_id: str,
    db: AsyncSession,
    **kwargs,
) -> Optional[Memory]:
    mem = await get_memory(memory_id, user_id, db)
    if not mem:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(mem, k):
            if k == "tags" and isinstance(v, list):
                v = json.dumps(v)
            setattr(mem, k, v)
    mem.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(mem)
    return mem


async def delete_memory(memory_id: str, user_id: str, db: AsyncSession) -> bool:
    mem = await get_memory(memory_id, user_id, db)
    if not mem:
        return False
    await db.delete(mem)
    await db.commit()
    return True


async def get_stats(user_id: str, db: AsyncSession) -> dict:
    """Get memory statistics for a user."""
    total_q = select(func.count(Memory.id)).where(Memory.user_id == user_id)
    archived_q = total_q.where(Memory.is_archived == 1)
    cat_q = (
        select(Memory.category, func.count(Memory.id))
        .where(Memory.user_id == user_id, Memory.is_archived == 0)
        .group_by(Memory.category)
    )
    total = (await db.execute(total_q)).scalar() or 0
    archived = (await db.execute(archived_q)).scalar() or 0
    cat_rows = (await db.execute(cat_q)).all()
    return {
        "total": total,
        "archived": archived,
        "active": total - archived,
        "by_category": {row[0]: row[1] for row in cat_rows},
    }


# ---- Search ----

async def search_memories(
    user_id: str,
    query: str,
    category: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = None,
) -> list[Memory]:
    """Keyword search across memories."""
    conditions = [
        Memory.user_id == user_id,
        Memory.is_archived == 0,
        or_(
            Memory.content.ilike(f"%{query}%"),
            Memory.tags.ilike(f"%{query}%"),
        ),
    ]
    if category:
        conditions.append(Memory.category == category)

    q = (
        select(Memory)
        .where(and_(*conditions))
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


# ---- Auto-extraction from conversations ----

_EXTRACTION_PROMPT = """Analyze this conversation and extract important information worth remembering.

Extract facts, decisions, preferences, and lessons. For each item:
- "content": what to remember
- "category": one of "daily" (conversation log), "long_term" (important fact), "preference" (user preference), "decision" (a decision made), "lesson" (lesson learned)
- "importance": 1-10

Only extract truly valuable information. Skip greetings and small talk.
Respond in JSON array: [{{"content": "...", "category": "...", "importance": N, "tags": ["..."]}}]

If nothing is worth remembering, return: []"""


async def extract_memories_from_conversation(
    user_id: str,
    messages: list[dict],
    session_maker: sessionmaker,
) -> int:
    """Auto-extract memories from a conversation. Returns number of memories created."""
    if len(messages) < 4:
        return 0

    # Build conversation text
    conv_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-12:]
    )

    try:
        prompt = _EXTRACTION_PROMPT + f"\n\nConversation:\n{conv_text}"
        parts: list[str] = []
        async for chunk in llm_service.generate(prompt, "", stream=False):
            parts.append(chunk)
        raw = "".join(parts).strip()

        # Parse JSON array
        match = json.loads(raw)
        if not isinstance(match, list) or not match:
            return 0

        count = 0
        async with session_maker() as db:
            for item in match[:5]:  # cap at 5 extractions per conversation
                content = item.get("content", "").strip()
                if not content or len(content) < 10:
                    continue
                await _do_create(
                    db, user_id, content,
                    category=item.get("category", "daily"),
                    source="auto_extract",
                    tags=item.get("tags"),
                    importance=item.get("importance", 5),
                )
                count += 1
        return count

    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Memory extraction failed: %s", exc)
        return 0


# ---- Memory consolidation (long-term from daily) ----

_CONSOLIDATION_PROMPT = """Review these daily memory notes and consolidate them into long-term insights.

For each insight:
- "content": distilled insight
- "category": "long_term" (factual), "preference" (user preference), "lesson" (lesson learned), "decision" (decision made)
- "importance": 1-10
- "tags": relevant tags

Skip redundant or trivial entries. Merge related entries.
Respond in JSON array: [{{"content": "...", "category": "...", "importance": N, "tags": ["..."]}}]"""


async def consolidate_daily_memories(
    user_id: str,
    session_maker: sessionmaker,
    days: int = 7,
) -> int:
    """Consolidate daily memories older than N days into long-term memories."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_maker() as db:
        q = (
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.category == "daily",
                Memory.is_archived == 0,
                Memory.created_at < cutoff,
            )
            .order_by(Memory.created_at.desc())
            .limit(50)
        )
        daily_mems = list((await db.execute(q)).scalars().all())

        if len(daily_mems) < 3:
            return 0

        notes_text = "\n".join(
            f"- [{m.created_at.strftime('%Y-%m-%d')}] {m.content}"
            for m in daily_mems
        )

        try:
            prompt = _CONSOLIDATION_PROMPT + f"\n\nDaily notes:\n{notes_text}"
            parts: list[str] = []
            async for chunk in llm_service.generate(prompt, "", stream=False):
                parts.append(chunk)
            raw = "".join(parts).strip()
            items = json.loads(raw)
            if not isinstance(items, list):
                return 0

            count = 0
            for item in items[:10]:
                content = item.get("content", "").strip()
                if not content or len(content) < 10:
                    continue
                await _do_create(
                    db, user_id, content,
                    category=item.get("category", "long_term"),
                    source="consolidation",
                    tags=item.get("tags"),
                    importance=item.get("importance", 6),
                )
                count += 1

            # Archive the processed daily memories
            for m in daily_mems:
                m.is_archived = 1
                m.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return count

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Memory consolidation failed: %s", exc)
            return 0


# ---- Get relevant memories for chat context ----

async def get_context_memories(
    user_id: str,
    query: str,
    db: AsyncSession,
    limit: int = 5,
) -> str:
    """Get formatted memory context to inject into chat prompts."""
    memories = await search_memories(user_id, query, limit=limit, db=db)
    if not memories:
        return ""

    lines = []
    for m in memories:
        tags = m.tags if m.tags else "[]"
        try:
            tags_str = ", ".join(json.loads(tags))
        except (json.JSONDecodeError, TypeError):
            tags_str = str(tags)
        lines.append(f"- [{m.category}] {m.content}")
        if tags_str:
            lines[-1] += f" (tags: {tags_str})"

    return "## User Memory Context\n" + "\n".join(lines)
