"""Memory CRUD routes."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Memory, get_db
from app.models.schemas import (
    MemoryCreate, MemoryUpdate, MemoryResponse, MemoryListResponse, MemoryStatsResponse,
)
from app.services.auth_service import get_current_user, get_optional_user
from app.models.database import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memories", tags=["memories"])



@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get memory statistics."""
    base_q = select(func.count(Memory.id)).where(Memory.user_id == current_user.id)
    total = (await db.execute(base_q)).scalar() or 0
    archived = (await db.execute(base_q.where(Memory.is_archived == 1))).scalar() or 0

    # By category
    cat_q = select(Memory.category, func.count(Memory.id)).where(
        Memory.user_id == current_user.id, Memory.is_archived == 0
    ).group_by(Memory.category)
    rows = (await db.execute(cat_q)).all()
    by_category = {r[0]: r[1] for r in rows}

    return MemoryStatsResponse(
        total=total,
        by_category=by_category,
        archived=archived,
        active=total - archived,
    )


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    category: Optional[str] = None,
    is_archived: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List memories with optional filters."""
    q = select(Memory).where(Memory.user_id == current_user.id)
    if category:
        q = q.where(Memory.category == category)
    if is_archived is not None:
        q = q.where(Memory.is_archived == is_archived)
    elif is_archived is None:
        q = q.where(Memory.is_archived == 0)
    if search:
        q = q.where(Memory.content.ilike(f"%{search}%"))

    # Count
    count_q = select(func.count(Memory.id))
    if category:
        count_q = count_q.where(Memory.user_id == current_user.id, Memory.category == category)
    else:
        count_q = count_q.where(Memory.user_id == current_user.id)
    if is_archived is not None:
        count_q = count_q.where(Memory.is_archived == is_archived)
    else:
        count_q = count_q.where(Memory.is_archived == 0)
    if search:
        count_q = count_q.where(Memory.content.ilike(f"%{search}%"))
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Memory.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return MemoryListResponse(
        memories=[MemoryResponse.model_validate(m) for m in rows],
        total=total,
    )


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    body: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new memory."""
    import uuid
    mem = Memory(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        category=body.category,
        content=body.content,
        source=body.source,
        source_id=body.source_id,
        tags=body.tags,
        importance=body.importance,
    )
    db.add(mem)
    await db.flush()
    await db.refresh(mem)
    return MemoryResponse.model_validate(mem)


@router.get("/{mem_id}", response_model=MemoryResponse)
async def get_memory(
    mem_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mem = await db.get(Memory, mem_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryResponse.model_validate(mem)


@router.put("/{mem_id}", response_model=MemoryResponse)
async def update_memory(
    mem_id: str,
    body: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mem = await db.get(Memory, mem_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    if body.content is not None:
        mem.content = body.content
    if body.category is not None:
        mem.category = body.category
    if body.tags is not None:
        mem.tags = body.tags
    if body.importance is not None:
        mem.importance = body.importance
    if body.is_archived is not None:
        mem.is_archived = body.is_archived
    await db.flush()
    await db.refresh(mem)
    return MemoryResponse.model_validate(mem)


@router.delete("/{mem_id}")
async def delete_memory(
    mem_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mem = await db.get(Memory, mem_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(mem)
    return {"message": "Memory deleted"}
