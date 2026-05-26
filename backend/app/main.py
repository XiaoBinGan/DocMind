from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.core.config import settings
from app.models.database import Base, engine, get_db, AsyncSessionLocal

async def _enable_wal():
    """Enable WAL mode for better concurrent access."""
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))


async def init_db():
    """Initialize the database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    # Enable WAL mode for better concurrent access
    await _enable_wal()
    
    await init_db()

    # Initialize settings service with session maker
    from app.services.settings_service import settings_service
    settings_service.init(AsyncSessionLocal)
    await settings_service.reload()

    # Ensure JWT secret key exists in DB
    from app.services.auth_service import ensure_jwt_secret_key
    await ensure_jwt_secret_key()

    # Ensure default admin user exists
    from app.services.auth_service import ensure_default_admin
    await ensure_default_admin()

    yield
    # Shutdown
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="DocMind - Reasoning-based RAG System",
    version="1.0.0",
    lifespan=lifespan
)

# Custom middleware imports
from app.core.middleware import RateLimitMiddleware, ErrorHandlingMiddleware

# CORS middleware - tightened security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Only frontend origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Rate limiting middleware (100 requests per minute per IP)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

# Global error handling middleware
app.add_middleware(ErrorHandlingMiddleware)

# Import routers after app is created
from app.routers import auth, documents, chat, models, settings as settings_router, memory, memories, token, api_catalog

# Include routers
app.include_router(auth.router, dependencies=[Depends(get_db)])
app.include_router(documents.router, dependencies=[Depends(get_db)])
app.include_router(chat.router, dependencies=[Depends(get_db)])
app.include_router(models.router, dependencies=[Depends(get_db)])
app.include_router(settings_router.router, dependencies=[Depends(get_db)])
app.include_router(memory.router, dependencies=[Depends(get_db)])
app.include_router(memories.router, dependencies=[Depends(get_db)])
app.include_router(token.router, dependencies=[Depends(get_db)])
app.include_router(api_catalog.router, dependencies=[Depends(get_db)])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "description": "DocMind - Reasoning-based RAG System built on PageIndex"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
