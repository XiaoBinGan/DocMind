"""Authentication service — JWT token management and password hashing."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User, Setting

logger = logging.getLogger(__name__)

# ── JWT config ──────────────────────────────────────────────────────────
JWT_SECRET_KEY_DB = "jwt_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Lazy secret resolution
_secret_key: Optional[str] = None


def _resolve_secret_key():
    """Resolve JWT secret from settings DB or generate new one."""
    global _secret_key
    if _secret_key:
        return _secret_key
    from app.services.settings_service import settings_service
    if settings_service and settings_service.ready and settings_service._cache:
        val = settings_service._cache.get(JWT_SECRET_KEY_DB, "")
        if val and len(val) >= 32:
            _secret_key = val
            return val
    # Generate new key
    _secret_key = secrets.token_hex(32)
    return _secret_key


SECRET_KEY = _resolve_secret_key()


# ── Password hashing ───────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── FastAPI security scheme ─────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[User]:
    """Return the current User or None — no 401 thrown."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except HTTPException:
        return None
    user_id: str = payload.get("sub")
    if not user_id:
        return None
    from app.main import async_session_maker
    async with async_session_maker() as session:
        try:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return user
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    """FastAPI dependency: extract and validate the current user from JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials)
    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    from app.main import async_session_maker
    async with async_session_maker() as session:
        try:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
        finally:
            await session.close()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def ensure_jwt_secret_key():
    """Ensure a JWT secret key exists in the settings DB. Generate one if not."""
    from app.main import async_session_maker
    from app.services.settings_service import settings_service
    async with async_session_maker() as session:
        row = await session.get(Setting, JWT_SECRET_KEY_DB)
        if not row or not row.value or len(row.value) < 32:
            new_key = secrets.token_hex(32)
            if row:
                row.value = new_key
            else:
                session.add(Setting(key=JWT_SECRET_KEY_DB, value=new_key))
            await session.commit()
            # Update cache
            if settings_service and settings_service.ready:
                settings_service._cache[JWT_SECRET_KEY_DB] = new_key
            global _SECRET_KEY
            _SECRET_KEY = new_key
            logger.info("JWT secret key generated and stored in DB")
        else:
            if settings_service and settings_service.ready:
                settings_service._cache[JWT_SECRET_KEY_DB] = row.value


async def ensure_default_admin():
    """Create the default admin user (admin / admin123) if it doesn't exist."""
    from app.main import async_session_maker
    import uuid
    async with async_session_maker() as session:
        try:
            result = await session.execute(select(User).where(User.username == "admin"))
            if result.scalar_one_or_none() is None:
                admin = User(
                    id=str(uuid.uuid4()),
                    username="admin",
                    email="admin@docmind.local",
                    hashed_password=hash_password("admin123"),
                    display_name="Administrator",
                    is_active=True,
                    is_admin=True,
                )
                session.add(admin)
                await session.commit()
                logger.info("Default admin user created (admin/admin123)")
            else:
                logger.debug("Admin user already exists")
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
