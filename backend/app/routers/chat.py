from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import uuid
import asyncio
import json as _json

from app.models.database import Conversation, Message, Document, User
from app.models.schemas import (
    ConversationResponse, ConversationListResponse,
    ChatRequest, ChatResponse, MessageResponse
)
from app.services.auth_service import get_current_user
from app.core.config import settings as _settings

router = APIRouter(prefix="/api", tags=["chat"])


async def get_db():
    async with __import__("app.main").main.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _doc_owner_check(db: AsyncSession, doc_id: str, current_user: User):
    """Return a filtered query for document ownership."""
    return select(Document).where(
        (Document.id == doc_id) &
        ((Document.user_id == current_user.id) | (Document.user_id == None))
    )


async def _verify_document_access(db: AsyncSession, doc_id: str, current_user: User):
    """Verify document access. Returns doc or None."""
    if not doc_id:
        return None
    q = _doc_owner_check(db, doc_id, current_user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def _build_context(db: AsyncSession, conv: Conversation, current_user: User, request_message: str):
    """Build document context with ownership check."""
    context, references = "", []
    if not conv.document_id:
        return context, references
    
    doc = await _verify_document_access(db, conv.document_id, current_user)
    if not doc:
        return context, references
    
    if doc.index_tree:
        from app.services.indexer import PageRetriever
        from app.services.parser import document_parser
        parsed = await document_parser.parse(doc.file_path)
        if parsed.get("success"):
            retriever = PageRetriever(doc.index_tree, parsed["pages"])
            retrieved = await retriever.retrieve(request_message, top_k=5)
            for r in retrieved:
                context += f"\n\n[Page {r['page']}]\n{r['content'][:1500]}"
                references.append({"page": r["page"], "reason": r.get("reason", ""), "preview": r["content"][:200]})
            if not retrieved:
                for i, page in enumerate(parsed["pages"][:3]):
                    content = page.get("content") if isinstance(page, dict) else str(page)
                    context += f"\n\n[Page {i+1}]\n{content[:1500]}"
    return context, references


async def _resolve_document(db: AsyncSession, conv: Conversation, current_user: User, request_message: str) -> bool:
    """Auto-match document with access control."""
    from app.services.intent_service import analyze_intent
    from app.services.doc_matcher import match_documents
    
    try:
        intent_result = await analyze_intent(request_message)
    except Exception:
        return False
    
    if not intent_result or intent_result.intent_type not in ("doc_query", "doc_comparison"):
        return False
    
    try:
        matches = await match_documents(request_message, intent_result.keywords, db)
        if matches:
            doc_ids = [m.document_id for m in matches]
            q = select(Document).where(
                Document.id.in_(doc_ids) &
                ((Document.user_id == current_user.id) | (Document.user_id == None))
            )
            result = await db.execute(q)
            accessible = result.scalars().all()
            if accessible:
                # Prefer user-owned docs
                for doc in accessible:
                    if doc.user_id == current_user.id:
                        conv.document_id = doc.id
                        return True
                conv.document_id = accessible[0].id
                return True
    except Exception:
        pass
    return False


# ── Non-streaming chat ──────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    document_id: Optional[str] = None,
    chat_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Conversation).where(Conversation.user_id == current_user.id).order_by(Conversation.updated_at.desc())
    if document_id:
        query = query.where(Conversation.document_id == document_id)
    if chat_type:
        if chat_type == "general":
            query = query.where(Conversation.chat_type == "general")
        elif chat_type == "doc_chat":
            query = query.where(Conversation.chat_type == "doc_chat")
    
    result = await db.execute(query.options(selectinload(Conversation.messages)))
    convs = result.scalars().all()
    
    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=c.id, title=c.title, user_id=c.user_id,
                chat_type=c.chat_type, document_id=c.document_id,
                messages=[MessageResponse(id=m.id, role=m.role, content=m.content,
                                          references=m.references, created_at=m.created_at) for m in c.messages],
                created_at=c.created_at, updated_at=c.updated_at
            ) for c in convs
        ],
        total=len(convs)
    )


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    title = body.get("title", "New conversation")
    chat_type = body.get("chat_type", "general")
    document_id = body.get("document_id")

    conv = Conversation(
        id=str(uuid.uuid4()),
        title=title[:50] if len(title) > 50 else title,
        user_id=current_user.id,
        document_id=document_id,
        chat_type=chat_type
    )
    db.add(conv)
    await db.flush()

    return ConversationResponse(
        id=conv.id, title=conv.title, user_id=conv.user_id,
        chat_type=conv.chat_type, document_id=conv.document_id,
        messages=[],
        created_at=conv.created_at, updated_at=conv.updated_at
    )


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == current_user.id
        ).options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationResponse(
        id=conv.id, title=conv.title, user_id=conv.user_id,
        chat_type=conv.chat_type, document_id=conv.document_id,
        messages=[MessageResponse(id=m.id, role=m.role, content=m.content,
                                  references=m.references, created_at=m.created_at) for m in conv.messages],
        created_at=conv.created_at, updated_at=conv.updated_at
    )


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    await db.commit()
    return {"message": "Conversation deleted"}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get a response (non-streaming)."""
    from app.services.llm import llm_service
    
    # Get or create conversation
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.user_id == current_user.id
            ).options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Verify document access
        if conv.document_id:
            doc = await _verify_document_access(db, conv.document_id, current_user)
            if not doc:
                conv.document_id = None  # user lost access
    else:
        conv = Conversation(
            id=str(uuid.uuid4()),
            title=(request.message[:50] + "..") if len(request.message) > 50 else request.message,
            user_id=current_user.id,
            document_id=request.document_id,
            chat_type=request.chat_type or ("doc_chat" if request.document_id else "general")
        )
        db.add(conv)
        await db.flush()
    
    # Save user message
    user_msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user", content=request.message)
    db.add(user_msg)
    await db.flush()
    
    # Build history
    history = ""
    if conv.messages:
        for m in conv.messages[-10:]:
            tag = "User" if m.role == "user" else "Assistant"
            history += f"\n{tag}: {m.content}"
    
    # Auto-match document
    await _resolve_document(db, conv, current_user, request.message)
    
    # Build context
    context, references = await _build_context(db, conv, current_user, request.message)
    
    # Build prompt
    system_prompt = """You are DocMind, an AI assistant specialized in analyzing documents.
Answer questions accurately based on document content. Cite specific pages when providing information."""
    
    if context:
        user_prompt = f"DOCUMENT CONTEXT:{context}\n\nCONVERSATION HISTORY:{history}\n\nUSER QUESTION: {request.message}\n\nPlease answer based on the document context."
    else:
        user_prompt = f"USER QUESTION: {request.message}"
    
    # Generate response
    response_text = ""
    async for chunk in llm_service.generate(system_prompt, user_prompt, stream=False):
        response_text += chunk
    
    # Record token usage
    prompt_tokens, completion_tokens, total_tokens = llm_service.last_usage
    if total_tokens > 0:
        try:
            from app.routers.token import record_token_usage
            await record_token_usage(
                user_id=current_user.id,
                conversation_id=conv.id,
                model_name=llm_service._last_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                db=db,  # pass current session to avoid lock contention
            )
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning("Failed to record token usage: %s", e)
    
    # Save assistant message
    assistant_msg = Message(
        id=str(uuid.uuid4()), conversation_id=conv.id, role="assistant",
        content=response_text, references=references if references else None
    )
    db.add(assistant_msg)
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(assistant_msg)
    
    return ChatResponse(
        conversation_id=conv.id,
        message=MessageResponse(id=assistant_msg.id, role="assistant", content=assistant_msg.content,
                                references=assistant_msg.references, created_at=assistant_msg.created_at)
    )


# ── Streaming chat ──────────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Stream chat response using Server-Sent Events."""
    from app.services.indexer import PageRetriever
    from app.services.parser import document_parser
    from app.services.llm import llm_service
    from app.services.intent_service import analyze_intent
    from app.services.doc_matcher import match_documents
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    conversation_id = ""
    message_id = str(uuid.uuid4())
    
    async def event_generator():
        nonlocal conversation_id
        engine = create_async_engine(_settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        try:
            async with async_session() as session:
                # Get or create conversation
                if request.conversation_id:
                    result = await session.execute(
                        select(Conversation).where(
                            Conversation.id == request.conversation_id,
                            Conversation.user_id == current_user.id
                        )
                    )
                    conv = result.scalar_one_or_none()
                    if not conv:
                        yield f"event: error\ndata: Conversation not found\n\n"
                        return
                    if conv.document_id:
                        doc = await _verify_document_access(session, conv.document_id, current_user)
                        if not doc:
                            conv.document_id = None
                else:
                    conv = Conversation(
                        id=str(uuid.uuid4()),
                        title=request.message[:50] + "..",
                        user_id=current_user.id,
                        document_id=request.document_id,
                        chat_type=request.chat_type or ("doc_chat" if request.document_id else "general")
                    )
                    session.add(conv)
                    await session.commit()
                    await session.flush()
                
                conversation_id = conv.id
                
                # Save user message
                user_msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id, role="user", content=request.message)
                session.add(user_msg)
                await session.commit()
                yield f"event: user_message\ndata: {user_msg.id}\n\n"
                
                # Build history
                history = ""
                if request.conversation_id:
                    hist = await session.execute(
                        select(Message).where(Message.conversation_id == conv.id)
                        .order_by(Message.created_at.asc())
                    )
                    for m in hist.scalars().all()[-10:]:
                        tag = "User" if m.role == "user" else "Assistant"
                        history += f"\n{tag}: {m.content}"
                
                # Auto-match + verify
                await _resolve_document(session, conv, current_user, request.message)
                context, references = await _build_context(session, conv, current_user, request.message)
                
                # Intent
                try:
                    ir = await analyze_intent(request.message)
                    yield f"event: intent\ndata: {_json.dumps(ir.to_dict(), ensure_ascii=False)}\n\n"
                except Exception:
                    pass
                
                # Generate
                system_prompt = "You are DocMind, an AI assistant specialized in analyzing documents."
                user_prompt = f"DOCUMENT CONTEXT:{context}\n\nHISTORY:{history}\n\nQUESTION: {request.message}" if context else f"QUESTION: {request.message}"
                
                full_response = ""
                try:
                    async for chunk in llm_service.generate(system_prompt, user_prompt, stream=True):
                        full_response += chunk
                        # JSON-encode chunk to keep the data line single-line.
                        # Newlines inside chunk are escaped as \n in JSON, so SSE
                        # parsing is safe and the frontend can JSON-decode to restore them.
                        yield f"event: chunk\ndata: {_json.dumps({'t': chunk}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                except Exception as exc:
                    if not full_response:
                        full_response = f"[Error: {exc}]"
                    yield f"event: error\ndata: {exc}\n\n"
                
                # Save
                assistant_msg = Message(id=message_id, conversation_id=conv.id, role="assistant",
                                        content=full_response, references=references if references else None)
                session.add(assistant_msg)
                conv.updated_at = datetime.utcnow()
                await session.commit()
                
                # Record token usage
                pt, ct, tt = llm_service.last_usage
                if tt > 0 and conversation_id:
                    try:
                        from app.routers.token import record_token_usage
                        await record_token_usage(
                            user_id=current_user.id,
                            conversation_id=conversation_id,
                            model_name=llm_service._last_model,
                            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
                        )
                    except Exception as _e:
                        pass
                
                yield f"event: done\ndata: {assistant_msg.id}\n\n"
                yield f"event: references\ndata: {_json.dumps(references or [], ensure_ascii=False)}\n\n"
                yield f"event: conversation_id\ndata: {conversation_id}\n\n"
        except Exception as gen_exc:
            import logging as _ll
            _ll.getLogger(__name__).error("Stream generator error: %s", gen_exc, exc_info=True)
            yield f"event: error\ndata: {gen_exc}\n\n"
        finally:
            await engine.dispose()
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# (end of chat.py)

