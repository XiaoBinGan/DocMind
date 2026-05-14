from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
import os
import uuid
import aiofiles

from app.models.database import Document, User
from app.models.schemas import DocumentResponse, DocumentListResponse, IndexStatusResponse, IndexNode
from app.services.auth_service import get_current_user
from app.services.parser import document_parser

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def get_db():
    """Dependency to get database session."""
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


def _doc_filter_query(current_user: User, include_public: bool = True):
    """Return a filtered query that only shows user's own docs (and public ones)."""
    q = select(Document).where(
        (Document.user_id == current_user.id) |
        (Document.user_id == None)  # include any public/unowned docs
    )
    return q


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload a new document owned by the current user."""
    if not document_parser.is_supported(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {', '.join(document_parser.get_supported_types())}"
        )
    
    from app.core.config import settings
    
    unique_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    safe_filename = f"{unique_id}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    doc = Document(
        id=unique_id,
        name=file.filename,
        file_path=file_path,
        file_type=ext,
        file_size=len(content),
        user_id=current_user.id,  # 绑定上传者为所有者
        index_status="pending"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    background_tasks.add_task(index_document, unique_id)
    
    return DocumentResponse(
        id=doc.id,
        name=doc.name,
        file_type=doc.file_type,
        file_size=doc.file_size,
        page_count=doc.page_count,
        index_status=doc.index_status,
        index_tree=None,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )


async def index_document(doc_id: str):
    """Background task to index a document."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.services.indexer import page_indexer
    from app.services.settings_service import settings_service
    from app.core.config import settings
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    if not settings_service.ready:
        settings_service.init(async_session)
        await settings_service.reload()
    
    async with async_session() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        
        if not doc:
            await engine.dispose()
            return
        
        try:
            doc.index_status = "indexing"
            await session.commit()
            
            index_result = await page_indexer.build_index(doc.file_path)
            
            if index_result.get("success"):
                doc.index_status = "ready"
                doc.index_tree = index_result.get("index_tree")
                doc.page_count = index_result.get("page_count", 0)
            else:
                doc.index_status = "error"
                doc.error_message = index_result.get("error")
            
            await session.commit()
            
        except Exception as e:
            doc.index_status = "error"
            doc.error_message = str(e)
            await session.commit()
        
        await engine.dispose()


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents owned by or public to current user."""
    q = _doc_filter_query(current_user)
    result = await db.execute(q.order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    
    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=d.id,
                name=d.name,
                file_type=d.file_type,
                file_size=d.file_size,
                page_count=d.page_count,
                index_status=d.index_status,
                index_tree=IndexNode(**d.index_tree) if d.index_tree else None,
                created_at=d.created_at,
                updated_at=d.updated_at
            )
            for d in docs
        ],
        total=len(docs)
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a document (must be owner or public)."""
    q = select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse(
        id=doc.id,
        name=doc.name,
        file_type=doc.file_type,
        file_size=doc.file_size,
        page_count=doc.page_count,
        index_status=doc.index_status,
        index_tree=IndexNode(**doc.index_tree) if doc.index_tree else None,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document (must be owner or admin)."""
    q = select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except Exception:
        pass
    
    await db.delete(doc)
    await db.commit()
    
    return {"message": "Document deleted"}


@router.post("/{doc_id}/reindex", response_model=IndexStatusResponse)
async def reindex_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reindex a document (must be owner or public)."""
    q = select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc.index_status = "pending"
    await db.commit()
    
    background_tasks.add_task(index_document, doc_id)
    
    return IndexStatusResponse(document_id=doc_id, status="pending")


@router.get("/{doc_id}/index/status", response_model=IndexStatusResponse)
async def get_index_status(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the indexing status of a document (must be owner or public)."""
    q = select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return IndexStatusResponse(
        document_id=doc_id,
        status=doc.index_status,
        error_message=doc.error_message
    )


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a document file (must be owner or public)."""
    q = select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )
    result = await db.execute(q)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        doc.file_path,
        filename=doc.name,
        media_type="application/octet-stream"
    )
