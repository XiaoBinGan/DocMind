"""Document matcher — match user queries to relevant documents."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Document

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    document_id: str
    document_name: str
    relevance_score: float
    match_reason: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Enhanced keyword extraction with POS tagging --------------------------

# Common Chinese stopwords (extended)
_STOPWORDS_ZH = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "什么", "怎么", "如何", "哪", "那", "这个", "那个", "吗", "呢",
    "吧", "啊", "可以", "能", "请", "帮", "想", "把", "被", "让",
    "用", "对", "从", "以", "及", "等", "中", "与", "或", "但",
    "如果", "因为", "所以", "然后", "虽然", "但是", "不过",
    "而", "或", "且", "并", "之", "其", "所", "为", "与",
}

# Common entity patterns
_ENTITY_PATTERNS = [
    re.compile(r'(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'),  # English proper nouns
    re.compile(r'([\u4e00-\u9fff]{2,8}(?:公司|集团|大学|医院|机构|组织|系统|平台|项目|方案|计划|报告|合同|协议))'),  # Organizations
    re.compile(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)'),  # Dates
    re.compile(r'([A-Z][A-Za-z0-9_-]{2,})'),  # Abbreviations/acronyms
]

# POS patterns for Chinese
_POS_PATTERNS = {
    "noun": re.compile(r'[\u4e00-\u9fff_a-zA-Z]{2,}'),  # Nouns (simplified, Chinese + English words)
    "number": re.compile(r'\d+(?:\.\d+)?%?'),  # Numbers and percentages
    "measure": re.compile(r'(?:个|条|件|项|笔|次|份|张|篇|章|页|段|节|部|本|册|卷)'),  # Chinese measure words
}


def _extract_entities(text: str) -> list[str]:
    """Extract named entities from text using pattern matching."""
    entities = []
    
    for pattern in _ENTITY_PATTERNS:
        matches = pattern.findall(text)
        entities.extend(matches)
    
    return list(dict.fromkeys(entities))  # Deduplicate while preserving order


def _extract_key_terms(text: str, include_entities: bool = True) -> list[str]:
    """Extract key terms from text with POS awareness.
    
    Uses jieba if available for Chinese word segmentation. Falls back to 
    regex-based extraction for English/mixed text.
    """
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
        words = list(jieba.cut(text))
        
        # Filter: remove stopwords, keep nouns/verbs/adjectives (length >= 2)
        key_terms = []
        for w in words:
            w = w.strip()
            if len(w) < 2:
                continue
            if w in _STOPWORDS_ZH:
                continue
            # Keep meaningful terms
            if any(c.isalpha() for c in w):
                key_terms.append(w)
        
        # Weight: prefer longer terms (compounds) and unique terms
        scored = {}
        for term in key_terms:
            score = len(term) * 0.5 + (1 if any(c.isupper() for c in term) else 0)
            scored[term] = max(scored.get(term, 0), score)
        
        # Sort by score descending, return unique terms
        sorted_terms = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [term for term, _ in sorted_terms[:20]]  # Limit to top 20 terms
        
    except ImportError:
        # Fallback: regex-based extraction
        terms = set()
        
        # Extract English words (2+ chars)
        english_words = re.findall(r'[A-Za-z]{2,}', text)
        terms.update(w.lower() for w in english_words)
        
        # Extract Chinese words (2+ chars)
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        for w in chinese_words:
            if w not in _STOPWORDS_ZH:
                terms.add(w)
        
        # Score terms by length (longer = more specific)
        scored = {t: len(t) for t in terms}
        sorted_terms = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        
        result = [term for term, _ in sorted_terms[:15]]
        
        # Add entities
        if include_entities:
            entities = _extract_entities(text)
            for e in entities:
                if e not in result:
                    result.append(e)
        
        return result


def _extract_keywords_with_pos(text: str, max_keywords: int = 10) -> list[dict]:
    """Extract keywords with POS tagging and confidence scoring.
    
    Returns list of {keyword, pos, confidence, is_entity} dicts.
    """
    key_terms = _extract_key_terms(text)
    entities = _extract_entities(text)
    
    result = []
    seen = set()
    
    # Add entities first (higher weight)
    for entity in entities[:5]:
        if entity not in seen:
            result.append({
                "keyword": entity,
                "pos": "entity",
                "confidence": 0.95,
                "is_entity": True
            })
            seen.add(entity)
    
    # Add key terms
    for term in key_terms:
        if term in seen:
            continue
        if len(result) >= max_keywords:
            break
        
        # Determine POS (simplified classification)
        if re.match(r'^\d', term):
            pos = "number"
            confidence = 0.9
        elif re.match(r'^[A-Z]', term):
            pos = "proper_noun"
            confidence = 0.85
        elif len(term) >= 4:
            pos = "compound_noun"
            confidence = 0.8
        else:
            pos = "noun"
            confidence = 0.7
        
        result.append({
            "keyword": term,
            "pos": pos,
            "confidence": confidence,
            "is_entity": False
        })
        seen.add(term)
    
    return result


# ---- Index tree utilities ---------------------------------------------


def _flatten_index_tree(node: dict, path: str = "") -> list[dict]:
    """Flatten index tree into list of (path, title, page_range)."""
    results = []
    title = node.get("title", "")
    level = node.get("level", 0)
    current_path = f"{path} > {title}" if path else title
    results.append({
        "path": current_path,
        "title": title,
        "level": level,
        "page_start": node.get("page_start", 0),
        "page_end": node.get("page_end", 0),
    })
    for child in node.get("children", []):
        results.extend(_flatten_index_tree(child, current_path))
    return results


def _enhanced_keyword_score(keywords: list[str], text: str, keyword_info: Optional[list[dict]] = None) -> float:
    """Enhanced keyword scoring with POS weighting and entity boosting.
    
    Args:
        keywords: List of keyword strings
        text: Text to score against
        keyword_info: Optional list of dicts with keyword metadata (pos, confidence, is_entity)
    
    Returns:
        Score between 0.0 and 1.0
    """
    if not keywords or not text:
        return 0.0
    
    text_lower = text.lower()
    total_weight = 0.0
    matched_weight = 0.0
    
    for i, kw in enumerate(keywords):
        kw_lower = kw.lower()
        
        # Base weight
        weight = 1.0
        
        # Apply POS/entity weighting if keyword_info provided
        if keyword_info and i < len(keyword_info):
            info = keyword_info[i]
            if info.get("is_entity", False):
                weight *= 2.0  # Entities are more important
            elif info.get("pos") in ["entity", "proper_noun", "compound_noun"]:
                weight *= 1.5  # Proper nouns and compounds are important
            elif info.get("pos") == "number":
                weight *= 1.2  # Numbers moderately important
            
            # Apply confidence weighting
            confidence = info.get("confidence", 0.7)
            weight *= confidence
        
        # Length weighting (longer keywords are more specific)
        weight *= min(len(kw) / 3.0, 2.0)  # Cap at 2x for very long keywords
        
        total_weight += weight
        
        # Check for exact match
        if kw_lower in text_lower:
            matched_weight += weight
        else:
            # Check for partial match (for Chinese/English mixed)
            # For Chinese: check character overlap
            if any('\u4e00' <= c <= '\u9fff' for c in kw):
                # Chinese keyword: check character overlap
                kw_chars = set(kw)
                text_chars = set(text)
                overlap = kw_chars & text_chars
                if overlap and len(overlap) / len(kw_chars) >= 0.5:
                    matched_weight += weight * 0.7  # Partial match penalty
            else:
                # English keyword: check word boundary matches
                words = re.findall(r'\b\w+\b', text_lower)
                if any(kw_lower in word for word in words):
                    matched_weight += weight * 0.8  # Partial match penalty
    
    if total_weight == 0:
        return 0.0
    
    return matched_weight / total_weight


def _semantic_overlap_score(keywords: list[str], text: str, keyword_info: Optional[list[dict]] = None) -> float:
    """Score based on semantic overlap with enhanced weighting."""
    return _enhanced_keyword_score(keywords, text, keyword_info)


async def match_documents(
    user_message: str,
    keywords: list[str],
    db: AsyncSession,
    user_id: Optional[str] = None,
    limit: int = 5,
) -> list[MatchResult]:
    """Match user query to documents. Uses keyword matching + optional LLM ranking."""
    # Get all ready documents
    query = select(Document).where(Document.index_status == "ready")
    result = await db.execute(query)
    docs = result.scalars().all()

    if not docs:
        return []

    # Phase 1: enhanced keyword matching with POS weighting
    # Extract keywords with POS information for better matching
    try:
        keyword_info = _extract_keywords_with_pos(user_message)
        enhanced_keywords = [kw["keyword"] for kw in keyword_info]
    except Exception:
        keyword_info = None
        enhanced_keywords = keywords
    
    scored: list[MatchResult] = []
    for doc in docs:
        # Build searchable text from document name + index tree titles only
        searchable = doc.name
        if doc.index_tree:
            flat = _flatten_index_tree(doc.index_tree)
            searchable += " " + " ".join(item["title"] for item in flat)

        # Score: enhanced keyword overlap with document name + index tree titles
        if keyword_info:
            score = _enhanced_keyword_score(enhanced_keywords, searchable, keyword_info)
        else:
            score = _enhanced_keyword_score(keywords, searchable, None)

        # Bonus: entity overlap
        entity_score = 0.0
        if keyword_info:
            entities = [kw["keyword"] for kw in keyword_info if kw.get("is_entity")]
            if entities:
                entity_hits = sum(1 for e in entities if e.lower() in searchable.lower())
                entity_score = entity_hits / len(entities) * 0.3  # Bonus for entity matches

        # Bonus: partial match — how many keyword chars appear in searchable
        if score == 0 and (keywords or enhanced_keywords):
            all_kw = enhanced_keywords or keywords
            partial_hits = 0
            for k in all_kw:
                kw_chars = set(k)
                if len(kw_chars) >= 2:
                    overlap = kw_chars & set(searchable)
                    if len(overlap) / len(kw_chars) >= 0.5:
                        partial_hits += 1
            score = partial_hits / len(all_kw) * 0.5  # Lower weight for partial

        combined = min(score + entity_score, 1.0)
        if combined > 0:
            scored.append(MatchResult(
                document_id=doc.id,
                document_name=doc.name,
                relevance_score=round(combined, 3),
                match_reason=f"keyword match (score={combined:.2f})",
            ))

    # Sort by relevance
    scored.sort(key=lambda x: x.relevance_score, reverse=True)

    # Phase 2: LLM-based matching when keyword matching is weak
    # When in a doc Q&A system and user sends a query, always try to find a doc
    if not scored or scored[0].relevance_score < 0.5:
        try:
            # Build candidate list from all docs if keyword matches are too weak
            rerank_candidates = scored if scored else [
                MatchResult(
                    document_id=doc.id,
                    document_name=doc.name,
                    relevance_score=0.0,
                    match_reason="no keyword match, LLM fallback",
                )
                for doc in docs[:10]  # Limit to 10 docs for LLM
            ]
            if len(rerank_candidates) >= 1:
                scored = await _llm_rerank(user_message, rerank_candidates, limit)
        except Exception as exc:
            logger.warning("LLM fallback matching failed: %s", exc)
    elif len(scored) > 1 and len(scored) <= 10:
        # Keyword matches are good — LLM re-rank for better precision
        try:
            scored = await _llm_rerank(user_message, scored, limit)
        except Exception as exc:
            logger.warning("LLM reranking failed: %s", exc)

    return scored[:limit]


async def _llm_rerank(
    user_message: str,
    candidates: list[MatchResult],
    limit: int,
) -> list[MatchResult]:
    """Use LLM to re-rank document matches."""
    from app.services.llm import llm_service

    doc_list = "\n".join(
        f"{i+1}. [{c.document_name}] (id: {c.document_id}) — {c.match_reason}"
        for i, c in enumerate(candidates)
    )
    prompt = f"""Rank the following documents by relevance to the user's question.

User question: {user_message}

Documents:
{doc_list}

Respond in JSON: {{"ranked_ids": ["id1", "id2", ...], "reasons": {{"id1": "reason", ...}}}}"""
    parts: list[str] = []
    async for chunk in llm_service.generate(prompt, "", stream=False):
        parts.append(chunk)
    raw = "".join(parts).strip()

    import re
    # Find JSON with balanced braces (handles nested objects)
    start = raw.find('{')
    if start < 0:
        return candidates
    depth = 0
    end = start
    for i in range(start, len(raw)):
        if raw[i] == '{':
            depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end <= start:
        return candidates
    try:
        data = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return candidates
    ranked_ids = data.get("ranked_ids", [])
    reasons = data.get("reasons", {})

    # Reorder
    id_map = {c.document_id: c for c in candidates}
    reranked = []
    for doc_id in ranked_ids:
        if doc_id in id_map:
            c = id_map[doc_id]
            c.match_reason = reasons.get(doc_id, c.match_reason)
            reranked.append(c)

    # Include any missing
    for c in candidates:
        if c.document_id not in {r.document_id for r in reranked}:
            reranked.append(c)

    return reranked[:limit]
