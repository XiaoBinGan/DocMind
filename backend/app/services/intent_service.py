"""Intent analysis service — classify user messages and route to appropriate handler."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from app.services.llm import llm_service

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    intent_type: str  # doc_query | general_chat | doc_comparison | doc_summary | doc_search | doc_translate | ambiguous
    confidence: float
    keywords: list[str] = field(default_factory=list)
    matched_document_ids: list[str] = field(default_factory=list)
    reasoning: str = ""
    metadata: dict = field(default_factory=dict)  # 扩展元数据，如目标语言、文档ID等

    def to_dict(self) -> dict:
        return asdict(self)


# ---- quick keyword heuristics (no LLM needed) --------------------------

_DOC_KEYWORDS_ZH = re.compile(
    r"(文档|文件|报告|论文|合同|表格|清单|手册|说明书|目录|附件|内容|摘要|章节|页码|第\d+页|这段|这篇|上文|下文)"
)
_COMPARISON_KEYWORDS_ZH = re.compile(
    r"(对比|比较|区别|差异|相同点|不同点|哪个好|两者|各个|分别|vs|VS)"
)
_SUMMARY_KEYWORDS_ZH = re.compile(
    r"(总结|总结一下|概括|归纳|提炼|梳理|汇总|概要|概述|结论|要点)"
)
_SEARCH_KEYWORDS_ZH = re.compile(
    r"(搜索|查找|寻找|找.*关于|有没有|有哪些|搜索.*文件|找.*文件|列出)"
)
_TRANSLATE_KEYWORDS_ZH = re.compile(
    r"(翻译|译成|译为|英文|中文|日语|韩语|法语|德语|translate|翻成|英文版|中文版|双语)"
)
_GENERAL_KEYWORDS_ZH = re.compile(
    r"(你好|嗨|hello|hi|谢谢|再见|你是谁|你能做什么|帮我|解释|是什么意思|怎么理解|讲一下|说说|介绍一下|什么是|为什么)"
)


def _quick_classify(text: str) -> Optional[str]:
    """Fast regex-based classification; returns None if uncertain."""
    t = text.strip().lower()
    if _COMPARISON_KEYWORDS_ZH.search(t):
        return "doc_comparison"
    if _SUMMARY_KEYWORDS_ZH.search(t):
        return "doc_summary"
    if _TRANSLATE_KEYWORDS_ZH.search(t):
        return "doc_translate"
    if _SEARCH_KEYWORDS_ZH.search(t):
        return "doc_search"
    if _DOC_KEYWORDS_ZH.search(t):
        return "doc_query"
    if _GENERAL_KEYWORDS_ZH.search(t):
        return "general_chat"
    # Short noun phrases (no explicit markers) — in a doc Q&A system,
    # bare terms are almost always document queries
    if len(t) >= 2 and not _GENERAL_KEYWORDS_ZH.search(t):
        return "doc_query"
    return None


# ---- keyword extraction ------------------------------------------------

def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Simple keyword extraction — removes common stopwords."""
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
    except ImportError:
        # Fallback: simple character-based keyword extraction without jieba
        return _simple_keyword_fallback(text, top_n)
    STOPWORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "什么", "怎么", "如何", "哪", "那", "这个", "那个", "吗", "呢",
        "吧", "啊", "可以", "能", "请", "帮", "想", "把", "被", "让",
        "用", "对", "从", "以", "及", "等", "中", "与", "或", "但",
        "如果", "因为", "所以", "然后", "虽然", "但是", "不过",
    }
    words = [w for w in jieba.cut(text) if len(w) >= 2 and w not in STOPWORDS]
    # deduplicate while preserving order
    seen = set()
    unique = []
    for w in words:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:top_n]


def _simple_keyword_fallback(text: str, top_n: int = 8) -> list[str]:
    """Fallback keyword extraction without jieba — splits on spaces and punctuation."""
    import re
    # Remove common punctuation and split
    cleaned = re.sub(r"[^\w\s]", " ", text)
    # Filter short words and deduplicate
    seen = set()
    result = []
    for w in cleaned.split():
        if len(w) >= 2 and w not in seen:
            seen.add(w)
            result.append(w)
    return result[:top_n]


# ---- JSON parsing utilities --------------------------------------------

def _parse_intent_json(raw_response: str) -> Optional[dict]:
    """Robust JSON parsing with multiple fallback strategies."""
    # Method 1: Direct JSON parsing
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        pass
    
    # Method 2: Extract from markdown code blocks
    code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Method 3: Find outermost balanced braces
    start = raw_response.find('{')
    if start >= 0:
        depth = 0
        for i in range(start, len(raw_response)):
            if raw_response[i] == '{':
                depth += 1
            elif raw_response[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = raw_response[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
    
    # Method 4: Try to fix common JSON issues
    # Remove leading/trailing non-JSON text
    lines = raw_response.strip().split('\n')
    for i, line in enumerate(lines):
        if '{' in line:
            candidate = '\n'.join(lines[i:])
            # Try to find closing }
            end = candidate.rfind('}')
            if end > 0:
                candidate = candidate[:end+1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
    
    return None


def _calibrate_confidence(intent_type: str, raw_confidence: float, quick_classifier: Optional[str]) -> float:
    """Calibrate confidence based on quick classifier agreement."""
    if quick_classifier is None:
        # No quick classifier match, reduce confidence slightly
        return max(0.3, raw_confidence * 0.9)
    
    if intent_type == quick_classifier:
        # Quick classifier agrees, increase confidence
        return min(1.0, raw_confidence * 1.1)
    else:
        # Quick classifier disagrees, reduce confidence significantly
        return max(0.2, raw_confidence * 0.7)


# ---- LLM-based intent classification -----------------------------------

_INTENT_PROMPT = """You are an intent classifier for a document Q&A system.

Given a user message, classify the intent into one of:
- "doc_query": user wants to ask about specific document content, answer specific questions
- "general_chat": user is making small talk or asking general knowledge questions unrelated to documents
- "doc_comparison": user wants to compare content across multiple documents or sections
- "doc_summary": user wants a summary, overview, or key points extraction from documents
- "doc_search": user wants to search/find/locate specific documents or information within documents
- "doc_translate": user wants to translate document content to another language
- "ambiguous": cannot determine intent with confidence

Important: Be precise with confidence:
- 0.9-1.0: Very clear intent (explicit document reference or obvious small talk)
- 0.7-0.89: Fairly clear intent
- 0.4-0.69: Some ambiguity but leaning one way
- 0.0-0.39: Highly uncertain — mark as "ambiguous"

Also extract up to 5 important keywords from the message.
Provide metadata when applicable (e.g., target_language for translate, target_document for search).

Respond in JSON only:
{{"intent_type": "...", "confidence": 0.0-1.0, "keywords": ["..."], "reasoning": "...", "metadata": {{}}}}

User message: {message}

If conversation history is provided, use it for context:
{history}"""


async def analyze_intent(
    user_message: str,
    conversation_history: Optional[list[dict]] = None,
) -> IntentResult:
    """Classify user intent. Falls back to keyword heuristics if LLM fails."""
    # Quick path
    quick = _quick_classify(user_message)
    try:
        keywords = extract_keywords(user_message)
    except Exception:
        keywords = []

    try:
        history_str = ""
        if conversation_history:
            # 使用更多历史对话上下文
            history_str = json.dumps(
                conversation_history[-10:], ensure_ascii=False
            )

        prompt = _INTENT_PROMPT.format(
            message=user_message, history=history_str or "(none)"
        )
        parts: list[str] = []
        async for chunk in llm_service.generate(prompt, "", stream=False):
            parts.append(chunk)
        raw = "".join(parts).strip()
        logger.info("Intent LLM raw response: %s", raw[:500])

        # Parse JSON with enhanced multi-strategy extraction
        data = _parse_intent_json(raw)
        
        if data is not None:
            # Validate intent_type against known types
            valid_types = {"doc_query", "general_chat", "doc_comparison", 
                          "doc_summary", "doc_search", "doc_translate", "ambiguous"}
            intent_type = data.get("intent_type", "ambiguous")
            if intent_type not in valid_types:
                intent_type = "ambiguous"
            
            # Confidence calibration — apply floor/ceiling based on quick classifier agreement
            raw_confidence = float(data.get("confidence", 0.5))
            confidence = _calibrate_confidence(intent_type, raw_confidence, quick)
            
            return IntentResult(
                intent_type=intent_type,
                confidence=confidence,
                keywords=data.get("keywords", keywords),
                reasoning=data.get("reasoning", ""),
                metadata=data.get("metadata", {}),
            )
        else:
            logger.warning("Intent: could not extract JSON from LLM response")
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)

    # Fallback — when uncertain, mark as ambiguous instead of blindly defaulting
    fallback_type = quick if quick else "ambiguous"
    return IntentResult(
        intent_type=fallback_type,
        confidence=0.5 if quick else 0.3,
        keywords=keywords,
        reasoning="fallback heuristic",
        metadata={},
    )


# ──────────────────────────────────────────────────────────────
# Self-RAG Routing Integration (P0 升级)
# ──────────────────────────────────────────────────────────────

async def analyze_intent_with_routing(
    user_message: str,
    conversation_history: Optional[list[dict]] = None,
    retrieved_content: str = "",
    documents_available: bool = True,
) -> dict:
    """Intent analysis + Self-RAG hybrid routing.

    Extended version of analyze_intent() that performs:
    1. Standard intent classification
    2. Self-RAG relevance check on retrieved content
    3. Hybrid routing decision (answer / decline / retry / clarify)

    Returns:
        Dict with keys:
        - intent_result: IntentResult from standard classification
        - routing_decision: RoutingDecision from hybrid router
        - final_action: "answer" | "decline" | "retry_with_expansion" | "ask_clarification"
    """
    from app.services.query_rewriter import hybrid_route

    # Step 1: Standard intent classification
    intent_result = await analyze_intent(user_message, conversation_history)

    # Step 2: Hybrid routing
    routing_decision = await hybrid_route(
        query=user_message,
        intent_type=intent_result.intent_type,
        intent_confidence=intent_result.confidence,
        retrieved_content=retrieved_content,
        documents_available=documents_available,
    )

    # Step 3: Determine final action
    if not routing_decision.should_answer:
        if routing_decision.should_retry_with_expansion:
            final_action = "retry_with_expansion"
        elif routing_decision.fallback_message:
            final_action = "decline"
        else:
            final_action = "ask_clarification"
    else:
        final_action = "answer"

    return {
        "intent_result": intent_result,
        "routing_decision": routing_decision,
        "final_action": final_action,
    }
