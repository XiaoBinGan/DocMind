"""Intent handlers — route intents to appropriate processors."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, Conversation, Document
from app.services.intent_service import IntentResult
from app.services.reasoning_service import reasoning_service, ReasoningResult
from app.services.doc_matcher import match_documents, MatchResult
from app.services.knowledge_graph import knowledge_graph_service
from app.services.llm import llm_service

logger = logging.getLogger(__name__)


@dataclass
class HandlerResult:
    """Result from an intent handler."""
    success: bool
    response: str
    metadata: Dict[str, Any]
    requires_user_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    confirmation_options: Optional[List[Dict]] = None
    next_step: Optional[str] = None


class IntentRouter:
    """Routes intents to appropriate handlers."""
    
    def __init__(self):
        self.handlers: Dict[str, Callable] = {
            "doc_query": self._handle_doc_query,
            "general_chat": self._handle_general_chat,
            "doc_comparison": self._handle_doc_comparison,
            "doc_summary": self._handle_doc_summary,
            "doc_search": self._handle_doc_search,
            "doc_translate": self._handle_doc_translate,
            "ambiguous": self._handle_ambiguous,
        }
        
        # Handler priorities (lower = higher priority)
        self.priorities = {
            "doc_query": 1,
            "doc_comparison": 2,
            "doc_summary": 3,
            "doc_search": 4,
            "doc_translate": 5,
            "general_chat": 6,
            "ambiguous": 7,
        }
    
    async def route(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Route intent to appropriate handler."""
        handler = self.handlers.get(intent.intent_type)
        if not handler:
            logger.warning(f"No handler for intent type: {intent.intent_type}")
            return await self._handle_ambiguous(
                intent, user_message, conversation, current_user, db, conversation_history
            )
        
        try:
            return await handler(intent, user_message, conversation, current_user, db, conversation_history)
        except Exception as e:
            logger.error(f"Handler {intent.intent_type} failed: {e}")
            return HandlerResult(
                success=False,
                response=f"处理请求时出错: {str(e)}",
                metadata={"error": str(e), "intent": intent.intent_type}
            )
    
    async def _handle_doc_query(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle document query intent with reasoning-based retrieval."""
        # Step 1: Use reasoning service for true reasoning
        reasoning_result = await reasoning_service.reason_about_query(
            query=user_message,
            conversation_history=conversation_history,
            user_id=current_user.id,
            db_session=db
        )
        
        # Step 2: Get relevant documents with reasoning context
        relevant_docs = []
        if reasoning_result.relevant_document_ids:
            # Verify document access
            from sqlalchemy import select
            result = await db.execute(
                select(Document).where(
                    Document.id.in_(reasoning_result.relevant_document_ids) &
                    ((Document.user_id == current_user.id) | (Document.user_id == None))
                )
            )
            relevant_docs = result.scalars().all()
        
        # Step 3: If no reasoning-based docs found, fallback to keyword matching
        if not relevant_docs:
            matches = await match_documents(
                user_message,
                intent.keywords,
                db,
                current_user.id,
                limit=3
            )
            relevant_docs = []
            for match in matches:
                result = await db.execute(
                    select(Document).where(
                        Document.id == match.document_id &
                        ((Document.user_id == current_user.id) | (Document.user_id == None))
                    )
                )
                doc = result.scalar_one_or_none()
                if doc:
                    relevant_docs.append(doc)
        
        # Step 4: Determine if user confirmation is needed
        requires_confirmation = False
        confirmation_prompt = None
        confirmation_options = None
        
        if len(relevant_docs) > 1:
            # Multiple relevant docs found, ask user to choose
            requires_confirmation = True
            confirmation_prompt = f"我找到了 {len(relevant_docs)} 个相关文档。请选择要使用的文档："
            confirmation_options = [
                {
                    "id": doc.id,
                    "name": doc.name,
                    "description": f"相关度: {reasoning_result.confidence:.2f}" if reasoning_result.confidence > 0.5 else "基于关键词匹配"
                }
                for doc in relevant_docs[:3]  # Limit to top 3
            ]
            
            return HandlerResult(
                success=True,
                response="找到了多个相关文档，请确认使用哪个文档。",
                metadata={
                    "reasoning_result": reasoning_result,
                    "relevant_docs": [{"id": d.id, "name": d.name} for d in relevant_docs],
                    "reasoning_steps": [
                        {"type": s.step_type, "description": s.description, "confidence": s.confidence}
                        for s in reasoning_result.reasoning_steps
                    ]
                },
                requires_user_confirmation=requires_confirmation,
                confirmation_prompt=confirmation_prompt,
                confirmation_options=confirmation_options,
                next_step="await_document_selection"
            )
        
        # Step 5: Single or no document case
        if relevant_docs:
            # Single relevant document found
            selected_doc = relevant_docs[0]
            conversation.document_id = selected_doc.id
            
            return HandlerResult(
                success=True,
                response=f"已为您选择文档: {selected_doc.name}。正在准备回答...",
                metadata={
                    "selected_document": selected_doc.id,
                    "document_name": selected_doc.name,
                    "reasoning_confidence": reasoning_result.confidence,
                    "reasoning_steps": len(reasoning_result.reasoning_steps)
                },
                next_step="generate_answer"
            )
        else:
            # No relevant documents found
            return HandlerResult(
                success=True,
                response="未找到相关文档。您可以上传文档或尝试其他问题。",
                metadata={
                    "reasoning_result": reasoning_result,
                    "no_documents_found": True
                },
                next_step="suggest_upload"
            )
    
    async def _handle_general_chat(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle general chat intent."""
        # Clear document association for general chat
        conversation.document_id = None
        
        # Use LLM for general conversation
        system_prompt = "You are DocMind, a helpful AI assistant for document analysis and general conversation."
        user_prompt = f"User: {user_message}"
        
        response_text = ""
        async for chunk in llm_service.generate(system_prompt, user_prompt, stream=False):
            response_text += chunk
        
        return HandlerResult(
            success=True,
            response=response_text,
            metadata={
                "intent": "general_chat",
                "document_cleared": True
            }
        )
    
    async def _handle_doc_comparison(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle document comparison intent."""
        # Find multiple documents for comparison
        matches = await match_documents(
            user_message,
            intent.keywords,
            db,
            current_user.id,
            limit=5
        )
        
        # Filter accessible documents
        from sqlalchemy import select
        accessible_docs = []
        for match in matches:
            result = await db.execute(
                select(Document).where(
                    Document.id == match.document_id &
                    ((Document.user_id == current_user.id) | (Document.user_id == None))
                )
            )
            doc = result.scalar_one_or_none()
            if doc:
                accessible_docs.append({
                    "doc": doc,
                    "relevance": match.relevance_score
                })
        
        if len(accessible_docs) < 2:
            return HandlerResult(
                success=True,
                response="需要至少两个文档进行比较。请上传更多文档或指定要比较的文档。",
                metadata={
                    "found_docs": len(accessible_docs),
                    "requires_more_docs": True
                }
            )
        
        # Ask user to select documents for comparison
        return HandlerResult(
            success=True,
            response=f"找到了 {len(accessible_docs)} 个相关文档用于比较。请选择要比较的文档：",
            metadata={
                "available_docs": [
                    {
                        "id": item["doc"].id,
                        "name": item["doc"].name,
                        "relevance": item["relevance"]
                    }
                    for item in accessible_docs[:5]  # Limit to top 5
                ]
            },
            requires_user_confirmation=True,
            confirmation_prompt="请选择要比较的文档（至少选择2个）：",
            confirmation_options=[
                {
                    "id": item["doc"].id,
                    "name": item["doc"].name,
                    "description": f"相关度: {item['relevance']:.2f}"
                }
                for item in accessible_docs[:5]
            ],
            next_step="await_comparison_selection"
        )
    
    async def _handle_doc_summary(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle document summary intent."""
        # Find document for summarization
        matches = await match_documents(
            user_message,
            intent.keywords,
            db,
            current_user.id,
            limit=3
        )
        
        if not matches:
            return HandlerResult(
                success=True,
                response="未找到要总结的文档。请指定文档或上传文档。",
                metadata={"no_documents_found": True}
            )
        
        # Get accessible documents
        from sqlalchemy import select
        accessible_docs = []
        for match in matches:
            result = await db.execute(
                select(Document).where(
                    Document.id == match.document_id &
                    ((Document.user_id == current_user.id) | (Document.user_id == None))
                )
            )
            doc = result.scalar_one_or_none()
            if doc:
                accessible_docs.append({
                    "doc": doc,
                    "relevance": match.relevance_score
                })
        
        if not accessible_docs:
            return HandlerResult(
                success=True,
                response="没有可访问的文档用于总结。",
                metadata={"no_accessible_docs": True}
            )
        
        if len(accessible_docs) > 1:
            # Multiple documents found, ask user to choose
            return HandlerResult(
                success=True,
                response=f"找到了 {len(accessible_docs)} 个相关文档。请选择要总结的文档：",
                metadata={
                    "available_docs": [
                        {
                            "id": item["doc"].id,
                            "name": item["doc"].name,
                            "relevance": item["relevance"]
                        }
                        for item in accessible_docs
                    ]
                },
                requires_user_confirmation=True,
                confirmation_prompt="请选择要总结的文档：",
                confirmation_options=[
                    {
                        "id": item["doc"].id,
                        "name": item["doc"].name,
                        "description": f"相关度: {item['relevance']:.2f}"
                    }
                    for item in accessible_docs
                ],
                next_step="await_summary_selection"
            )
        
        # Single document case
        selected_doc = accessible_docs[0]["doc"]
        conversation.document_id = selected_doc.id
        
        return HandlerResult(
            success=True,
            response=f"已选择文档: {selected_doc.name}。正在生成总结...",
            metadata={
                "selected_document": selected_doc.id,
                "document_name": selected_doc.name,
                "action": "generate_summary"
            },
            next_step="generate_summary"
        )
    
    async def _handle_doc_search(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle document search intent."""
        # Use reasoning service for better search
        reasoning_result = await reasoning_service.reason_about_query(
            query=user_message,
            conversation_history=conversation_history,
            user_id=current_user.id,
            db_session=db
        )
        
        # Get search results
        matches = await match_documents(
            user_message,
            intent.keywords + reasoning_result.metadata.get("concepts", {}).get("key_concepts", []),
            db,
            current_user.id,
            limit=10
        )
        
        # Filter accessible documents
        from sqlalchemy import select
        accessible_docs = []
        for match in matches:
            result = await db.execute(
                select(Document).where(
                    Document.id == match.document_id &
                    ((Document.user_id == current_user.id) | (Document.user_id == None))
                )
            )
            doc = result.scalar_one_or_none()
            if doc:
                accessible_docs.append({
                    "doc": doc,
                    "relevance": match.relevance_score,
                    "match_reason": match.match_reason
                })
        
        if not accessible_docs:
            return HandlerResult(
                success=True,
                response="未找到相关文档。",
                metadata={
                    "reasoning_result": reasoning_result,
                    "no_documents_found": True
                }
            )
        
        # Format search results
        results_text = f"找到了 {len(accessible_docs)} 个相关文档：\n\n"
        for i, item in enumerate(accessible_docs[:5], 1):
            results_text += f"{i}. **{item['doc'].name}** (相关度: {item['relevance']:.2f})\n"
            results_text += f"   匹配原因: {item['match_reason']}\n\n"
        
        if len(accessible_docs) > 5:
            results_text += f"... 还有 {len(accessible_docs) - 5} 个结果\n"
        
        return HandlerResult(
            success=True,
            response=results_text,
            metadata={
                "search_results": [
                    {
                        "id": item["doc"].id,
                        "name": item["doc"].name,
                        "relevance": item["relevance"],
                        "match_reason": item["match_reason"]
                    }
                    for item in accessible_docs
                ],
                "reasoning_confidence": reasoning_result.confidence
            }
        )
    
    async def _handle_doc_translate(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle document translation intent."""
        # Extract target language from metadata or query
        target_language = intent.metadata.get("target_language")
        if not target_language:
            # Try to detect language from query
            lang_keywords = {
                "英文": "English",
                "中文": "Chinese",
                "日语": "Japanese",
                "韩语": "Korean",
                "法语": "French",
                "德语": "German",
                "西班牙语": "Spanish"
            }
            
            for keyword, lang in lang_keywords.items():
                if keyword in user_message:
                    target_language = lang
                    break
        
        if not target_language:
            target_language = "English"  # Default
        
        # Find document for translation
        matches = await match_documents(
            user_message,
            intent.keywords,
            db,
            current_user.id,
            limit=3
        )
        
        if not matches:
            return HandlerResult(
                success=True,
                response="未找到要翻译的文档。请指定文档或上传文档。",
                metadata={
                    "target_language": target_language,
                    "no_documents_found": True
                }
            )
        
        # Get accessible documents
        from sqlalchemy import select
        accessible_docs = []
        for match in matches:
            result = await db.execute(
                select(Document).where(
                    Document.id == match.document_id &
                    ((Document.user_id == current_user.id) | (Document.user_id == None))
                )
            )
            doc = result.scalar_one_or_none()
            if doc:
                accessible_docs.append({
                    "doc": doc,
                    "relevance": match.relevance_score
                })
        
        if not accessible_docs:
            return HandlerResult(
                success=True,
                response="没有可访问的文档用于翻译。",
                metadata={
                    "target_language": target_language,
                    "no_accessible_docs": True
                }
            )
        
        if len(accessible_docs) > 1:
            # Multiple documents found, ask user to choose
            return HandlerResult(
                success=True,
                response=f"找到了 {len(accessible_docs)} 个相关文档。请选择要翻译成{target_language}的文档：",
                metadata={
                    "target_language": target_language,
                    "available_docs": [
                        {
                            "id": item["doc"].id,
                            "name": item["doc"].name,
                            "relevance": item["relevance"]
                        }
                        for item in accessible_docs
                    ]
                },
                requires_user_confirmation=True,
                confirmation_prompt=f"请选择要翻译成{target_language}的文档：",
                confirmation_options=[
                    {
                        "id": item["doc"].id,
                        "name": item["doc"].name,
                        "description": f"相关度: {item['relevance']:.2f}"
                    }
                    for item in accessible_docs
                ],
                next_step="await_translation_selection"
            )
        
        # Single document case
        selected_doc = accessible_docs[0]["doc"]
        conversation.document_id = selected_doc.id
        
        return HandlerResult(
            success=True,
            response=f"已选择文档: {selected_doc.name}。正在准备翻译成{target_language}...",
            metadata={
                "selected_document": selected_doc.id,
                "document_name": selected_doc.name,
                "target_language": target_language,
                "action": "generate_translation"
            },
            next_step="generate_translation"
        )
    
    async def _handle_ambiguous(
        self,
        intent: IntentResult,
        user_message: str,
        conversation: Conversation,
        current_user: User,
        db: AsyncSession,
        conversation_history: Optional[List[Dict]] = None
    ) -> HandlerResult:
        """Handle ambiguous intent."""
        # Ask for clarification
        clarification_prompt = "我不太确定您的意图。请澄清：\n1. 您是想查询文档内容吗？\n2. 还是进行一般对话？\n3. 或者其他需求？"
        
        return HandlerResult(
            success=True,
            response=clarification_prompt,
            metadata={
                "intent": "ambiguous",
                "confidence": intent.confidence,
                "requires_clarification": True
            },
            requires_user_confirmation=True,
            confirmation_prompt="请选择您的意图：",
            confirmation_options=[
                {"id": "doc_query", "name": "查询文档内容", "description": "询问关于文档的问题"},
                {"id": "general_chat", "name": "一般对话", "description": "聊天或一般问题"},
                {"id": "doc_search", "name": "搜索文档", "description": "查找特定文档"},
                {"id": "other", "name": "其他", "description": "其他需求"}
            ],
            next_step="await_intent_clarification"
        )


# Singleton instance
intent_router = IntentRouter()