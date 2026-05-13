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
    r"(文档|文件|报告|论文|合同|表格|表格|清单|手册|说明书|目录|附件)"
)
_COMPARISON_KEYWORDS_ZH = re.compile(
    r"(对比|比较|区别|差异|相同点|不同点|哪个好|两者|各个|分别)"
)
_GENERAL_KEYWORDS_ZH = re.compile(
    r"(你好|嗨|hello|hi|谢谢|再见|你是谁|你能做什么|帮我|解释|是什么意思|怎么理解)"
)


def _quick_classify(text: str) -> Optional[str]:
    """Fast regex-based classification; returns None if uncertain."""
    t = text.strip().lower()
    if _GENERAL_KEYWORDS_ZH.search(t) and len(t) < 30:
        return "general_chat"
    if _COMPARISON_KEYWORDS_ZH.search(t):
        return "doc_comparison"
    if _DOC_KEYWORDS_ZH.search(t):
        return "doc_query"
    return None


# ---- keyword extraction ------------------------------------------------

def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Simple keyword extraction — removes common stopwords."""
    import jieba
    jieba.setLogLevel(logging.WARNING)
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


# ---- LLM-based intent classification -----------------------------------

_INTENT_PROMPT = """You are an intent classifier for a document Q&A system.

Given a user message, classify the intent into one of:
- "doc_query": user wants to ask about specific document content
- "general_chat": user is making small talk or asking general knowledge questions unrelated to documents
- "doc_comparison": user wants to compare content across multiple documents
- "ambiguous": cannot determine

Also extract up to 5 important keywords from the message.

Respond in JSON only:
{"intent_type": "...", "confidence": 0.0-1.0, "keywords": ["..."], "reasoning": "..."}

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
    keywords = extract_keywords(user_message)

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

        # extract JSON
        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return IntentResult(
                intent_type=data.get("intent_type", "ambiguous"),
                confidence=float(data.get("confidence", 0.5)),
                keywords=data.get("keywords", keywords),
                reasoning=data.get("reasoning", ""),
            )
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)

    # Fallback
    return IntentResult(
        intent_type=quick or "ambiguous",
        confidence=0.4,
        keywords=keywords,
        reasoning="fallback heuristic",
    )
