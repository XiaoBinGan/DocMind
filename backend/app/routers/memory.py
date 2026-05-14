"""Memory routes — CRUD, search, stats, and consolidation."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.database import Memory
from app.models.schemas import (
    MemoryCreate, MemoryUpdate, MemoryResponse,
    MemoryListResponse, MemoryStatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/memories", tags=["memory"])


async def get_db():
    from app.main import async_session_maker
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _mem_to_response(m: Memory) -> MemoryResponse:
    import json
    tags = None
    if m.tags:
        try:
            parsed = json.loads(m.tags)
            tags = parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, TypeError):
            tags = None
    return MemoryResponse(
        id=m.id,
        user_id=m.user_id,
        category=m.category,
        content=m.content,
        source=m.source,
        source_id=m.source_id,
        tags=tags,
        importance=m.importance,
        is_archived=m.is_archived,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    category: Optional[str] = Query(None, description="Filter by category"),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    from app.services.memory_service import list_memories as _list
    # TODO: inject user_id from auth token
    user_id = "default"
    memories, total = await _list(user_id, category, include_archived, limit, offset, db)
    return MemoryListResponse(
        memories=[_mem_to_response(m) for m in memories],
        total=total,
    )


@router.get("/stats", response_model=MemoryStatsResponse)
async def memory_stats(db: AsyncSession = Depends(get_db)):
    from app.services.memory_service import get_stats
    user_id = "default"
    stats = await get_stats(user_id, db)
    return MemoryStatsResponse(**stats)


@router.get("/search", response_model=MemoryListResponse)
async def search_memories(
    q: str = Query(..., min_length=1, description="Search query"),
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    from app.services.memory_service import search_memories as _search
    user_id = "default"
    memories = await _search(user_id, q, category, limit, db)
    return MemoryListResponse(memories=[_mem_to_response(m) for m in memories], total=len(memories))


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.memory_service import get_memory as _get
    user_id = "default"
    mem = await _get(memory_id, user_id, db)
    if not mem:
        raise HTTPException(404, "Memory not found")
    return _mem_to_response(mem)


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(req: MemoryCreate, db: AsyncSession = Depends(get_db)):
    from app.services.memory_service import create_memory
    user_id = "default"
    mem = await create_memory(
        user_id=user_id,
        content=req.content,
        category=req.category,
        source=req.source,
        source_id=req.source_id,
        tags=req.tags,
        importance=req.importance,
        db=db,
    )
    return _mem_to_response(mem)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(memory_id: str, req: MemoryUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.memory_service import update_memory as _update
    user_id = "default"
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    mem = await _update(memory_id, user_id, db, **updates)
    if not mem:
        raise HTTPException(404, "Memory not found")
    return _mem_to_response(mem)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.memory_service import delete_memory as _delete
    user_id = "default"
    ok = await _delete(memory_id, user_id, db)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"message": "Memory deleted"}


@router.post("/consolidate")
async def consolidate_memories(
    days: int = Query(7, ge=1, le=90, description="Consolidate daily notes older than N days"),
):
    from app.main import async_session_maker
    from app.services.memory_service import consolidate_daily_memories
    user_id = "default"
    count = await consolidate_daily_memories(user_id, async_session_maker, days=days)
    return {"message": f"Consolidated {count} long-term memories from daily notes", "created": count}
