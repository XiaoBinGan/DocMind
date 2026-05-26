"""Authentication routes — register, login, profile management."""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database import User, Conversation, Message, get_db
from app.models.schemas import (
    UserResponse, UserCreate, UserLogin, UserUpdate,
    TokenResponse, ChangePasswordRequest, UserToggleBody,
)
from app.services.auth_service import (
    hash_password, verify_password, create_token, get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])



# ── Helpers ─────────────────────────────────────────────────────────────

def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


# ── Routes ──────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user. Returns JWT token on success."""
    # Check username uniqueness
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Check email uniqueness if provided
    if body.email:
        existing_email = await db.execute(select(User).where(User.email == body.email))
        if existing_email.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Email already registered")

    import uuid
    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or body.username,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_token(user.id)
    return TokenResponse(token=token, user=_user_response(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with username + password. Returns JWT token."""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.updated_at = datetime.utcnow()
    await db.flush()

    token = create_token(user.id)
    return TokenResponse(token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return _user_response(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    if body.email is not None:
        # Check uniqueness
        existing = await db.execute(select(User).where(User.email == body.email, User.id != current_user.id))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = body.email

    current_user.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(current_user)
    return _user_response(current_user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    current_user.updated_at = datetime.utcnow()
    await db.flush()
    return {"message": "Password changed successfully"}


# ── Admin routes ─────────────────────────────────────────────


async def _require_admin(current_user: User = Depends(get_current_user)):
    """Ensure the current user is an admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/admin/users", response_model=list[dict])
async def admin_get_users(
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all users with conversation count (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    
    # Count conversations per user via subquery
    conv_counts = {}
    if users:
        user_ids = [u.id for u in users]
        conv_query = await db.execute(
            select(Conversation.user_id, func.count(Conversation.id))
            .where(Conversation.user_id.in_(user_ids))
            .group_by(Conversation.user_id)
        )
        conv_counts = {uid: count for uid, count in conv_query}
    
    resp = []
    for u in users:
        conv_count = conv_counts.get(u.id, 0) or 0
        resp.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "display_name": u.display_name,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "conversation_count": conv_count,
            "created_at": u.created_at.isoformat(),
            "updated_at": u.updated_at.isoformat(),
        })
    return resp


@router.post("/admin/users/{user_id}")
async def admin_update_user(
    user_id: str,
    body: UserToggleBody,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle user status or admin role (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-deadmin / self-deactivate
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")

    if body.action == "activate":
        target.is_active = True
    elif body.action == "deactivate":
        target.is_active = False
    elif body.action == "grant_admin":
        target.is_admin = True
    elif body.action == "revoke_admin":
        target.is_admin = False
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    target.updated_at = datetime.utcnow()
    await db.flush()
    return {
        "message": f"User {body.action} successful",
        "user_id": target.id,
        "is_active": target.is_active,
        "is_admin": target.is_admin,
    }


@router.get("/admin/conversations")
async def admin_get_conversations(
    user_id: str = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all conversations, optionally filtered by user_id (admin only)."""
    query = select(Conversation).options(
        selectinload(Conversation.messages),
        selectinload(Conversation.user)
    ).order_by(Conversation.updated_at.desc())
    if user_id:
        query = query.where(Conversation.user_id == user_id)
    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total.scalar()
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    convs = result.scalars().all()
    resp = []
    for c in convs:
        msg_count = len(c.messages) if c.messages else 0
        user = c.user
        user_name = user.username if user else "unknown"
        resp.append({
            "id": c.id,
            "title": c.title or "",
            "user_id": c.user_id or "",
            "username": user_name,
            "chat_type": c.chat_type,
            "document_id": c.document_id,
            "message_count": msg_count,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        })
    return {"conversations": resp, "total": total, "page": page, "page_size": page_size}


@router.get("/admin/conversations/{conv_id}")
async def admin_get_conversation_detail(
    conv_id: str,
    current_user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full conversation detail including all messages (admin only)."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "id": conv.id,
        "title": conv.title or "",
        "user_id": conv.user_id or "",
        "chat_type": conv.chat_type,
        "document_id": conv.document_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "references": m.references,
                "created_at": m.created_at.isoformat(),
            }
            for m in conv.messages
        ],
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }
