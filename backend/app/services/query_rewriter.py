"""Query Rewriter — HyDE + Decomposition + Self-RAG Routing.

P0 升级：解决意图误判问题。
- HyDE (Hypothetical Document Embedding)：生成假设文档，用假设文档的嵌入向量检索
- Query Decomposition：将复杂查询拆解为原子子查询
- Self-RAG Routing：检索后自检相关性 / 可回答性，不相关时拒答
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from app.services.llm import llm_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# HyDE: Hypothetical Document Embedding
# ──────────────────────────────────────────────────────────────

_HYDE_PROMPT = """You are helping a document Q&A system. Write a short hypothetical document passage
(3-5 sentences) that would answer the user's question IF it existed in the document collection.

DO NOT actually answer the question. Instead, write what a relevant document section might look like.

User question: {query}

Hypothetical passage:"""


async def generate_hyde_passage(query: str) -> str:
    """Generate a hypothetical document passage via LLM.

    The generated passage captures the expected language and structure
    of a relevant document, making it a better search query than the
    original user question alone.
    """
    prompt = _HYDE_PROMPT.format(query=query)
    try:
        passage = await llm_service.generate(prompt)
        passage = passage.strip().strip('"').strip("'")
        # Fallback: if LLM returns something too short, use original query
        if len(passage) < 20:
            logger.warning("HyDE passage too short, falling back to original query")
            return query
        return passage
    except Exception as exc:
        logger.warning("HyDE generation failed: %s", exc)
        return query  # graceful fallback


# ──────────────────────────────────────────────────────────────
# Query Decomposition
# ──────────────────────────────────────────────────────────────

_DECOMPOSE_PROMPT = """Break down the user's compound question into atomic sub-questions.
Each sub-question should be answerable by searching a single section of a document.

Rules:
- Output ONLY a JSON array of strings, no other text.
- Each sub-question must be self-contained and specific.
- If the question is already simple, return a single-element array.
- Maximum 5 sub-questions.

User question: {query}

JSON array:"""


async def decompose_query(query: str) -> List[str]:
    """Decompose a complex query into atomic sub-queries via LLM.

    Returns a list of sub-queries. If decomposition fails or the query
    is already simple, returns the original query as a single-element list.
    """
    prompt = _DECOMPOSE_PROMPT.format(query=query)
    try:
        result = await llm_service.generate(prompt)
        # Extract JSON array
        json_match = re.search(r"\[.*\]", result, re.DOTALL)
        if json_match:
            sub_queries = json.loads(json_match.group())
            if isinstance(sub_queries, list) and len(sub_queries) > 0:
                return sub_queries[:5]
    except Exception as exc:
        logger.warning("Query decomposition failed: %s", exc)
    return [query]


# ──────────────────────────────────────────────────────────────
# Self-RAG Routing: post-retrieval relevance check
# ──────────────────────────────────────────────────────────────

@dataclass
class SelfRAGResult:
    """Result of Self-RAG self-check."""
    is_relevant: bool
    is_supported: bool
    confidence: float
    explanation: str
    suggested_action: str  # "answer" | "decline" | "ask_clarification"


_SELF_RAG_PROMPT = """You are a Self-RAG verifier for a document Q&A system. Given:
1. The user's question
2. The retrieved document content

Decide whether the retrieved content is:
- RELEVANT: Does the content address the question topic?
- SUPPORTED: Does the content contain enough evidence to answer the question?

Respond in JSON format ONLY:
{{
    "is_relevant": true/false,
    "is_supported": true/false,
    "confidence": 0.0-1.0,
    "explanation": "Brief explanation of your judgment",
    "suggested_action": "answer" | "decline" | "ask_clarification"
}}

"suggested_action" rules:
- "answer": if both is_relevant and is_supported are true
- "decline": if is_relevant is false (completely off-topic)
- "ask_clarification": if is_relevant is true but is_supported is false (partially relevant but insufficient)

User question: {query}

Retrieved content (truncated):
{retrieved_content}

JSON response:"""


async def self_rag_check(
    query: str,
    retrieved_content: str,
    max_chars: int = 3000,
) -> SelfRAGResult:
    """Post-retrieval self-check: is the retrieved content relevant and sufficient?

    Args:
        query: Original user question
        retrieved_content: Concatenated retrieved document chunks
        max_chars: Max characters to feed into the verifier (avoid token overflow)

    Returns:
        SelfRAGResult with relevance judgment and suggested action.
    """
    # Truncate retrieved content to avoid token overflow
    truncated = retrieved_content[:max_chars] if len(retrieved_content) > max_chars else retrieved_content
    if not truncated.strip():
        return SelfRAGResult(
            is_relevant=False,
            is_supported=False,
            confidence=0.0,
            explanation="No content retrieved",
            suggested_action="decline",
        )

    prompt = _SELF_RAG_PROMPT.format(query=query, retrieved_content=truncated)
    try:
        raw = await llm_service.generate(prompt)
        # Robust JSON extraction (same strategy as intent_service)
        parsed = _parse_json(raw)
        if parsed:
            return SelfRAGResult(
                is_relevant=bool(parsed.get("is_relevant", False)),
                is_supported=bool(parsed.get("is_supported", False)),
                confidence=float(parsed.get("confidence", 0.5)),
                explanation=str(parsed.get("explanation", "")),
                suggested_action=str(parsed.get("suggested_action", "decline")),
            )
    except Exception as exc:
        logger.warning("Self-RAG check failed: %s", exc)

    # Default: assume relevant if we got content
    return SelfRAGResult(
        is_relevant=True,
        is_supported=True,
        confidence=0.5,
        explanation="Fallback (Self-RAG LLM check failed)",
        suggested_action="answer",
    )


# ──────────────────────────────────────────────────────────────
# Hybrid Routing Decision
# ──────────────────────────────────────────────────────────────

@dataclass
class RoutingDecision:
    """Hybrid routing decision combining intent + Self-RAG results."""
    intent_type: str
    confidence: float
    should_answer: bool
    should_retry_with_expansion: bool
    fallback_message: Optional[str] = None
    hyde_passage: Optional[str] = None
    sub_queries: List[str] = field(default_factory=list)


async def hybrid_route(
    query: str,
    intent_type: str,
    intent_confidence: float,
    retrieved_content: str,
    documents_available: bool,
) -> RoutingDecision:
    """Hybrid routing: intent classification + Self-RAG verification.

    Decision matrix:
    | Intent           | Self-RAG relevant | Self-RAG supported | Action              |
    |------------------|-------------------|-------------------|---------------------|
    | doc_query        | yes               | yes               | answer              |
    | doc_query        | yes               | no                | retry with HyDE     |
    | doc_query        | no                | -                 | decline             |
    | general_chat     | -                 | -                 | answer (no RAG)     |
    | ambiguous        | -                 | -                 | ask clarification   |

    Returns:
        RoutingDecision with final routing action.
    """
    # General chat / ambiguous — skip RAG verification
    if intent_type in ("general_chat", "ambiguous"):
        if intent_type == "ambiguous":
            return RoutingDecision(
                intent_type=intent_type,
                confidence=intent_confidence,
                should_answer=False,
                should_retry_with_expansion=False,
                fallback_message="我不太确定你的问题与文档中的内容相关，能具体说明一下吗？",
            )
        return RoutingDecision(
            intent_type=intent_type,
            confidence=intent_confidence,
            should_answer=True,
            should_retry_with_expansion=False,
        )

    # Document-related intents: run Self-RAG check
    if not documents_available:
        return RoutingDecision(
            intent_type=intent_type,
            confidence=intent_confidence,
            should_answer=False,
            should_retry_with_expansion=False,
            fallback_message="当前知识库中没有相关文档，请先上传文档后再提问。",
        )

    rag_result = await self_rag_check(query, retrieved_content)

    if rag_result.is_relevant and rag_result.is_supported:
        # Generate HyDE passage for better embedding retrieval
        hyde_passage = await generate_hyde_passage(query)
        sub_queries = await decompose_query(query)
        return RoutingDecision(
            intent_type=intent_type,
            confidence=max(intent_confidence, rag_result.confidence),
            should_answer=True,
            should_retry_with_expansion=False,
            hyde_passage=hyde_passage,
            sub_queries=sub_queries,
        )

    if rag_result.is_relevant and not rag_result.is_supported:
        # Partially relevant — retry with HyDE expansion
        hyde_passage = await generate_hyde_passage(query)
        return RoutingDecision(
            intent_type=intent_type,
            confidence=rag_result.confidence,
            should_answer=False,
            should_retry_with_expansion=True,
            hyde_passage=hyde_passage,
        )

    # Not relevant at all — decline
    return RoutingDecision(
        intent_type=intent_type,
        confidence=rag_result.confidence,
        should_answer=False,
        should_retry_with_expansion=False,
        fallback_message=f"抱歉，知识库中的文档内容与你的问题不相关。{rag_result.explanation}",
    )


# ──────────────────────────────────────────────────────────────
# JSON Parsing Utility
# ──────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Optional[dict]:
    """Robust JSON extraction (mirrors intent_service parsing strategy)."""
    # Method 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Method 2: from markdown code block
    code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass
    # Method 3: find outermost braces
    start = raw.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None