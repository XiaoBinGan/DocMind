from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import uuid
import asyncio

from app.models.database import Conversation, Message, Document
from app.models.schemas import (
    ConversationResponse, ConversationListResponse,
    ChatRequest, ChatResponse, MessageResponse
)
from app.services.intent_service import IntentResult

router = APIRouter(prefix="/api", tags=["chat"])


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


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(document_id: Optional[str] = None, chat_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """List all conversations, optionally filtered by document_id or chat_type."""
    query = select(Conversation).order_by(Conversation.updated_at.desc())
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
                id=c.id,
                title=c.title,
                user_id=c.user_id,
                chat_type=c.chat_type,
                document_id=c.document_id,
                messages=[
                    MessageResponse(id=m.id, role=m.role, content=m.content,
                                   references=m.references, created_at=m.created_at)
                    for m in c.messages
                ],
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in convs
        ],
        total=len(convs)
    )


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific conversation."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id).options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        chat_type=conv.chat_type,
        document_id=conv.document_id,
        messages=[
            MessageResponse(id=m.id, role=m.role, content=m.content,
                           references=m.references, created_at=m.created_at)
            for m in conv.messages
        ],
        created_at=conv.created_at,
        updated_at=conv.updated_at
    )


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a conversation."""
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    await db.delete(conv)
    await db.commit()
    return {"message": "Conversation deleted"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message and get a response (non-streaming)."""
    from app.services.indexer import PageRetriever
    from app.services.parser import document_parser
    from app.services.llm import llm_service
    
    # Get or create conversation
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == request.conversation_id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        # Get default user for conversation ownership
        from app.models.database import User as _U
        default_user = await db.execute(select(_U).limit(1))
        default_user_id = default_user.scalar_one_or_none()
        _uid = default_user_id.id if default_user_id else None

        conv = Conversation(
            id=str(uuid.uuid4()),
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
            user_id=_uid,
            document_id=request.document_id,
            chat_type=request.chat_type or ("doc_chat" if request.document_id else "general")
        )
        db.add(conv)
        await db.flush()
    
    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="user",
        content=request.message
    )
    db.add(user_msg)
    await db.flush()
    
    # Build conversation history
    history = ""
    if conv.messages:
        recent = conv.messages[-10:]
        for m in recent:
            if m.role == "user":
                history += f"\nUser: {m.content}"
            else:
                history += f"\nAssistant: {m.content}"
    
    # Get document context
    context, references = "", []
    if conv.document_id:
        doc_result = await db.execute(select(Document).where(Document.id == conv.document_id))
        doc = doc_result.scalar_one_or_none()
        
        if doc:
            doc_info = f"\n[Document Info]\nName: {doc.name}\nPages: {doc.page_count}\nType: {doc.file_type}"
            
            if doc.index_tree:
                parsed = await document_parser.parse(doc.file_path)
                if parsed.get("success"):
                    retriever = PageRetriever(doc.index_tree, parsed["pages"])
                    retrieved = await retriever.retrieve(request.message, top_k=5)
                    
                    for r in retrieved:
                        context += f"\n\n[Page {r['page']}]\n{r['content'][:1500]}"
                        references.append({"page": r["page"], "reason": r.get("reason", ""), "preview": r["content"][:200]})
                    
                    if not retrieved:
                        for i, page in enumerate(parsed["pages"][:3]):
                            context += f"\n\n[Page {i+1}]\n{(page["content"] if isinstance(page, dict) else str(page))[:1500]}"
                else:
                    context = doc_info
            else:
                context = doc_info
    
    # ── Intent analysis + doc matching ──
    intent_result = None
    try:
        from app.services.intent_service import analyze_intent
        intent_result = await analyze_intent(request.message)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("Intent analysis failed: %s", exc)

    # Auto-select document if none specified
    if not conv.document_id and intent_result and intent_result.intent_type in ("doc_query", "doc_comparison"):
        try:
            from app.services.doc_matcher import match_documents
            matches = await match_documents(request.message, intent_result.keywords, db)
            if matches:
                best = matches[0]
                conv.document_id = best.document_id
                await db.flush()
                # Build context for matched document
                from app.services.indexer import PageRetriever
                from app.services.parser import document_parser
                doc_result = await db.execute(select(Document).where(Document.id == best.document_id))
                doc = doc_result.scalar_one_or_none()
                if doc and doc.index_tree:
                    parsed = await document_parser.parse(doc.file_path)
                    if parsed.get("success"):
                        retriever = PageRetriever(doc.index_tree, parsed["pages"])
                        retrieved = await retriever.retrieve(request.message, top_k=5)
                        for r in retrieved:
                            context += f"\n\n[Page {r['page']}]\n{r['content'][:1500]}"
                            references.append({"page": r["page"], "reason": r.get("reason", ""), "preview": r["content"][:200]})
        except Exception as exc:
            import logging; logging.getLogger(__name__).warning("Doc matching failed: %s", exc)

    # Build prompt
    system_prompt = """You are DocMind, an AI assistant specialized in analyzing documents.
Answer questions accurately based on document content. Cite specific pages when providing information.

When answering questions about classifications, categories, or tables:
1. Identify the specific classification criteria mentioned in the document
2. List all categories and their definitions clearly
3. Reference the exact table or section where this information is found
4. Explain the relationships between different categories"""
    
    if context:
        user_prompt = f"DOCUMENT CONTEXT:{context}\n\nCONVERSATION HISTORY:{history}\n\nUSER QUESTION: {request.message}\n\nPlease answer based on the document context. If the question involves classifications or categories, be specific about the criteria and relationships."
    else:
        user_prompt = f"USER QUESTION: {request.message}"
    
    # Generate response
    response_text = ""
    async for chunk in llm_service.generate(system_prompt, user_prompt, stream=False):
        response_text += chunk
    
    # Save assistant message
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=response_text,
        references=references if references else None
    )
    db.add(assistant_msg)
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(assistant_msg)
    
    return ChatResponse(
        conversation_id=conv.id,
        message=MessageResponse(
            id=assistant_msg.id,
            role="assistant",
            content=assistant_msg.content,
            references=assistant_msg.references,
            created_at=assistant_msg.created_at
        )
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response using Server-Sent Events."""
    from fastapi.responses import StreamingResponse
    from app.services.indexer import PageRetriever
    from app.services.parser import document_parser
    from app.services.llm import llm_service
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    conversation_id = ""
    message_id = str(uuid.uuid4())
    
    async def event_generator():
        nonlocal conversation_id
        
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        try:
         async with async_session() as session:
            # Get or create conversation
            if request.conversation_id:
                result = await session.execute(
                    select(Conversation).where(Conversation.id == request.conversation_id)
                )
                conv = result.scalar_one_or_none()
            else:
                # Get default user for conversation ownership
                from app.models.database import User as _U
                default_user = await session.execute(select(_U).limit(1))
                default_user_id = default_user.scalar_one_or_none()
                _uid = default_user_id.id if default_user_id else None

                conv = Conversation(
                    id=str(uuid.uuid4()),
                    title=request.message[:50] + "...",
                    user_id=_uid,
                    document_id=request.document_id,
                    chat_type=request.chat_type or ("doc_chat" if request.document_id else "general")
                )
                session.add(conv)
                await session.commit()
                await session.flush()

            conversation_id = conv.id
            
            # Save user message
            user_msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                role="user",
                content=request.message
            )
            session.add(user_msg)
            await session.commit()
            
            yield f"event: user_message\ndata: {user_msg.id}\n\n"
            
            # Build conversation history — explicit query to avoid lazy load after commit
            history = ""
            if request.conversation_id:
                hist_result = await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.asc())
                )
                recent = hist_result.scalars().all()[-10:]
                for m in recent:
                    if m.role == "user":
                        history += f"\nUser: {m.content}"
                    else:
                        history += f"\nAssistant: {m.content}"
            
            # Get context
            context, references = "", []
            if conv.document_id:
                doc_result = await session.execute(select(Document).where(Document.id == conv.document_id))
                doc = doc_result.scalar_one_or_none()
                
                if doc:
                    # 把文档基本信息附上
                    doc_info = f"\n[Document Info]\nName: {doc.name}\nPages: {doc.page_count}\nType: {doc.file_type}"
                    
                    if doc.index_tree:
                        parsed = await document_parser.parse(doc.file_path)
                        if parsed.get("success"):
                            retriever = PageRetriever(doc.index_tree, parsed["pages"])
                            retrieved = await retriever.retrieve(request.message, top_k=5)
                            
                            for r in retrieved:
                                context += f"\n\n[Page {r['page']}]\n{r['content'][:1500]}"
                                references.append({"page": r["page"], "reason": r.get("reason", ""), "preview": r["content"][:200]})
                            
                            if not retrieved:
                                # 检索不到内容时，取前 3 页作为 fallback
                                for i, page in enumerate(parsed["pages"][:3]):
                                    context += f"\n\n[Page {i+1}]\n{(page["content"] if isinstance(page, dict) else str(page))[:1500]}"
                        else:
                            # 解析失败时也附上文档名
                            context = doc_info
                    else:
                        # 没有索引树时也附上文档名
                        context = doc_info
            
            # ── Intent analysis + doc matching ──
            intent_result = None
            try:
                from app.services.intent_service import analyze_intent, _quick_classify, extract_keywords
                # Fast classification first (no LLM needed) for immediate UI feedback
                quick = _quick_classify(request.message)
                try:
                    kw = extract_keywords(request.message)
                except Exception:
                    kw = []
                intent_result = IntentResult(
                    intent_type=quick or "general_chat",
                    confidence=0.9 if quick else 0.3,
                    keywords=kw,
                    reasoning="quick heuristic",
                )
                # Send intent immediately so frontend can show it right away
                import json as _json
                yield f"event: intent\ndata: {_json.dumps(intent_result.to_dict(), ensure_ascii=False)}\n\n"
                
                # Then try LLM-based refinement
                try:
                    intent_result = await analyze_intent(request.message)
                    # Send refined intent to update frontend
                    yield f"event: intent\ndata: {_json.dumps(intent_result.to_dict(), ensure_ascii=False)}\n\n"
                except Exception as exc:
                    import logging as _log; _log.getLogger(__name__).warning("LLM intent refinement failed: %s", exc)
            except Exception as exc:
                import logging as _log; _log.getLogger(__name__).warning("Intent analysis failed: %s", exc)

            # Auto-select document if none specified
            if not conv.document_id and intent_result and intent_result.intent_type in ("doc_query", "doc_comparison"):
                try:
                    from app.services.doc_matcher import match_documents
                    matches = await match_documents(request.message, intent_result.keywords, session)
                    if matches:
                        best = matches[0]
                        conv.document_id = best.document_id
                        await session.commit()
                        # Build context for matched document
                        doc_result = await session.execute(select(Document).where(Document.id == best.document_id))
                        doc = doc_result.scalar_one_or_none()
                        if doc and doc.index_tree:
                            parsed = await document_parser.parse(doc.file_path)
                            if parsed.get("success"):
                                retriever = PageRetriever(doc.index_tree, parsed["pages"])
                                retrieved = await retriever.retrieve(request.message, top_k=5)
                                for r in retrieved:
                                    context += f"\n\n[Page {r['page']}]\n{r['content'][:1500]}"
                                    references.append({"page": r["page"], "reason": r.get("reason", ""), "preview": r["content"][:200]})
                except Exception as exc:
                    import logging as _log; _log.getLogger(__name__).warning("Doc matching failed: %s", exc)

            # Build prompt
            system_prompt = """You are DocMind, an AI assistant specialized in analyzing documents.
Answer questions accurately based on document content. Always respond in the same language the user uses."""
            
            if context:
                user_prompt = f"DOCUMENT CONTEXT:{context}\n\nCONVERSATION HISTORY:{history}\n\nUSER QUESTION: {request.message}\n\nPlease answer based on the document context."
            else:
                user_prompt = f"USER QUESTION: {request.message}"
            
            # Stream response
            full_response = ""
            try:
                async for chunk in llm_service.generate(system_prompt, user_prompt, stream=True):
                    full_response += chunk
                    yield f"event: chunk\ndata: {chunk}\n\n"
                    await asyncio.sleep(0)
            except Exception as stream_exc:
                import logging as _ll
                _ll.getLogger(__name__).error("LLM stream error: %s", stream_exc, exc_info=True)
                if not full_response:
                    full_response = f"[LLM 错误: {stream_exc}]"
                yield f"event: error\ndata: {stream_exc}\n\n"
            
            # Save final message
            assistant_msg = Message(
                id=message_id,
                conversation_id=conv.id,
                role="assistant",
                content=full_response,
                references=references if references else None
            )
            session.add(assistant_msg)
            conv.updated_at = datetime.utcnow()
            await session.commit()
            
            import json as _json
            yield f"event: done\ndata: {assistant_msg.id}\n\nevent: references\ndata: {_json.dumps(references if references else [], ensure_ascii=False)}\n\n"
            yield f"event: conversation_id\ndata: {conversation_id}\n\n"
        except Exception as gen_exc:
            import logging as _ll
            _ll.getLogger(__name__).error("Stream generator error: %s", gen_exc, exc_info=True)
            yield f"event: error\ndata: {gen_exc}\n\n"
        finally:
            await engine.dispose()
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Import settings at module level to avoid circular imports
from app.core.config import settings
