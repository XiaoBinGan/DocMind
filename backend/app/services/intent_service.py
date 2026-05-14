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
    intent_type: str  # doc_query | general_chat | doc_comparison | ambiguous
    confidence: float
    keywords: list[str] = field(default_factory=list)
    matched_document_ids: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---- quick keyword heuristics (no LLM needed) --------------------------

_DOC_KEYWORDS_ZH = re.compile(
    r"(文档|文件|报告|论文|合同|表格|清单|手册|说明书|目录|附件|内容|摘要|章节|页码|第\d+页|这段|这篇|上文|下文)"
)
_COMPARISON_KEYWORDS_ZH = re.compile(
    r"(对比|比较|区别|差异|相同点|不同点|哪个好|两者|各个|分别|vs|VS)"
)
_GENERAL_KEYWORDS_ZH = re.compile(
    r"(你好|嗨|hello|hi|谢谢|再见|你是谁|你能做什么|帮我|解释|是什么意思|怎么理解|讲一下|说说|介绍一下|什么是|为什么)"
)


def _quick_classify(text: str) -> Optional[str]:
    """Fast regex-based classification; returns None if uncertain."""
    t = text.strip().lower()
    if _COMPARISON_KEYWORDS_ZH.search(t):
        return "doc_comparison"
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


# ---- LLM-based intent classification -----------------------------------

_INTENT_PROMPT = """You are an intent classifier for a document Q&A system.

Given a user message, classify the intent into one of:
- "doc_query": user wants to ask about specific document content
- "general_chat": user is making small talk or asking general knowledge questions unrelated to documents
- "doc_comparison": user wants to compare content across multiple documents
- "ambiguous": cannot determine

Important: Be precise with confidence:
- 0.9-1.0: Very clear intent (explicit document reference or obvious small talk)
- 0.7-0.89: Fairly clear intent
- 0.4-0.69: Some ambiguity but leaning one way
- 0.0-0.39: Highly uncertain

Also extract up to 5 important keywords from the message.

Respond in JSON only:
{{"intent_type": "...", "confidence": 0.0-1.0, "keywords": ["..."], "reasoning": "..."}}

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
            history_str = json.dumps(
                conversation_history[-6:], ensure_ascii=False
            )

        prompt = _INTENT_PROMPT.format(
            message=user_message, history=history_str or "(none)"
        )
        parts: list[str] = []
        async for chunk in llm_service.generate(prompt, "", stream=False):
            parts.append(chunk)
        raw = "".join(parts).strip()
        logger.info("Intent LLM raw response: %s", raw[:500])

        # extract JSON — try to find a valid JSON object
        # Method 1: try parsing the whole response
        data = None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            pass
        
        # Method 2: extract JSON from markdown code block or surrounding text
        if data is None:
            # Look for ```json ... ``` blocks first
            code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if code_match:
                try:
                    data = json.loads(code_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Method 3: find outermost balanced braces
            if data is None:
                # Find the first { and match to its closing }
                start = raw.find('{')
                if start >= 0:
                    depth = 0
                    for i in range(start, len(raw)):
                        if raw[i] == '{':
                            depth += 1
                        elif raw[i] == '}':
                            depth -= 1
                            if depth == 0:
                                candidate = raw[start:i+1]
                                try:
                                    data = json.loads(candidate)
                                    break
                                except json.JSONDecodeError:
                                    pass
        
        if data is not None:
            return IntentResult(
                intent_type=data.get("intent_type", "ambiguous"),
                confidence=float(data.get("confidence", 0.5)),
                keywords=data.get("keywords", keywords),
                reasoning=data.get("reasoning", ""),
            )
        else:
            logger.warning("Intent: could not extract JSON from LLM response")
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)

    # Fallback — in a document Q&A system, when uncertain, default to doc_query
    fallback_type = quick if quick else "doc_query"
    return IntentResult(
        intent_type=fallback_type,
        confidence=0.5 if not quick else 0.6,
        keywords=keywords,
        reasoning="fallback heuristic",
    )
