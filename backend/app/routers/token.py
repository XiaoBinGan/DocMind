"""Token usage tracking — models + API endpoints."""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TokenUsage, User
from app.models.schemas import (
    TokenUsageResponse,
    TokenSummaryResponse,
)
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)


async def get_db():
    from app.main import async_session_maker
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
        finally:
            await session.close()


router = APIRouter(prefix="/api/token", tags=["token"])


async def _ensure_table(db: AsyncSession):
    await db.execute(select(func.count()).select_from(TokenUsage))


# ── public endpoints ──

@router.get("/my-usage")
async def my_usage(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_table(db)
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(TokenUsage)
        .where(TokenUsage.user_id == current_user.id, TokenUsage.created_at >= cutoff)
        .order_by(TokenUsage.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "user_id": i.user_id,
            "username": None,
            "conversation_id": i.conversation_id,
            "model_name": i.model_name,
            "prompt_tokens": i.prompt_tokens,
            "completion_tokens": i.completion_tokens,
            "total_tokens": i.total_tokens,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


@router.get("/my-summary")
async def my_summary(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_table(db)
    cutoff = datetime.utcnow() - timedelta(days=days)

    sub = (
        select(
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0),
            func.count(TokenUsage.id),
        )
        .where(TokenUsage.user_id == current_user.id, TokenUsage.created_at >= cutoff)
    )
    total_prompt, total_completion, total_all, turn_count = (await db.execute(sub)).one()

    daily_sub = (
        select(
            func.date(TokenUsage.created_at).label("day"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.count(TokenUsage.id), 0).label("turns"),
        )
        .where(TokenUsage.user_id == current_user.id, TokenUsage.created_at >= cutoff)
        .group_by(func.date(TokenUsage.created_at))
        .order_by(func.date(TokenUsage.created_at).desc())
    )
    daily_result = (await db.execute(daily_sub)).all()
    daily = [{"date": str(r[0]), "tokens": r[1], "turns": r[2]} for r in daily_result]

    return {
        "total_prompt": int(total_prompt),
        "total_completion": int(total_completion),
        "total_all": int(total_all),
        "turn_count": int(turn_count),
        "daily": daily,
    }


# ── admin endpoints ──

@router.get("/admin/usage")
async def admin_all_usage(
    user_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: view all users' token usage (or filter by user_id)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    await _ensure_table(db)
    cutoff = datetime.utcnow() - timedelta(days=days)

    base = (
        select(TokenUsage)
        .join(User, User.id == TokenUsage.user_id)
        .where(TokenUsage.created_at >= cutoff)
        .order_by(TokenUsage.created_at.desc())
    )
    if user_id:
        base = base.where(TokenUsage.user_id == user_id)

    count = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    base = base.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base)
    items = result.scalars().all()

    return [
        {
            "id": i.id,
            "user_id": i.user_id,
            "username": None,
            "conversation_id": i.conversation_id,
            "model_name": i.model_name,
            "prompt_tokens": i.prompt_tokens,
            "completion_tokens": i.completion_tokens,
            "total_tokens": i.total_tokens,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


@router.get("/admin/summary")
async def admin_summary(
    user_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: per-user token summary. Shows ALL users (even with 0 usage)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    await _ensure_table(db)
    cutoff = datetime.utcnow() - timedelta(days=days)

    # KEY FIX: put date filter in JOIN ON clause instead of WHERE.
    # WHERE on left-joined column filters out NULLs → turns LEFT JOIN into INNER JOIN.
    # Users with no token records still appear with 0s.
    join_cond = TokenUsage.user_id == User.id
    if user_id:
        join_cond = join_cond & (TokenUsage.user_id == user_id)

    stmt = (
        select(
            User.id,
            User.username,
            User.display_name,
            func.coalesce(func.sum(TokenUsage.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsage.completion_tokens), 0),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0),
            func.coalesce(func.count(TokenUsage.id), 0),
        )
        .join(TokenUsage, join_cond & (TokenUsage.created_at >= cutoff), isouter=True)
        .group_by(User.id, User.username, User.display_name)
    )

    rows = (await db.execute(stmt)).all()
    return [
        {
            "user_id": r[0],
            "username": r[1],
            "display_name": r[2],
            "prompt_tokens": int(r[3]),
            "completion_tokens": int(r[4]),
            "total_tokens": int(r[5]),
            "turn_count": int(r[6]),
        }
        for r in rows
    ]


# ── exported record function ──

def _record_sync(rec, db_url):
    """Synchronous recording in a dedicated sync session."""
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    engine = create_engine(db_url, connect_args={"timeout": 5, "check_same_thread": False})
    sync_session = sessionmaker(engine, expire_on_commit=False)()
    try:
        sync_session.add(rec)
        sync_session.commit()
    except Exception as e:
        sync_session.rollback()
        logger.warning("Failed to record token usage (sync): %s", e)
    finally:
        sync_session.close()
        engine.dispose()


async def record_token_usage(
    user_id: str,
    conversation_id: str | None,
    model_name: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    db: Optional[AsyncSession] = None,
):
    """Save a token usage record. Call after each chat turn."""
    rec = TokenUsage(
        user_id=user_id,
        conversation_id=conversation_id,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    
    if db is not None:
        db.add(rec)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning("Failed to record token usage (db): %s", e)
        return
    
    from app.main import engine as async_engine
    from app.core.config import settings
    db_url = settings.DATABASE_URL
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _record_sync, rec, db_url)
