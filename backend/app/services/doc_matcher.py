"""Document matcher — match user queries to relevant documents."""
from __future__ import annotations

import json
import logging
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


def _keyword_score(keywords: list[str], text: str) -> float:
    """Simple keyword overlap score."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for k in keywords if k.lower() in text_lower)
    return hits / len(keywords)


def _token_overlap_score(keywords: list[str], text: str) -> float:
    """Score based on how many keyword tokens appear in text (more granular)."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    matched = 0
    for k in keywords:
        if k.lower() in text_lower:
            matched += 1
    return matched / len(keywords)


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

    # Phase 1: keyword matching
    scored: list[MatchResult] = []
    for doc in docs:
        # Build searchable text from document name + index tree titles only
        searchable = doc.name
        if doc.index_tree:
            flat = _flatten_index_tree(doc.index_tree)
            searchable += " " + " ".join(item["title"] for item in flat)

        # Score: keyword overlap with document name + index tree titles
        score = _token_overlap_score(keywords, searchable)

        # Bonus: partial match — how many keyword chars appear in searchable
        if score == 0 and keywords:
            # Try each keyword individually for partial matches
            partial_hits = 0
            for k in keywords:
                kw_chars = set(k)
                if len(kw_chars) >= 2:
                    overlap = kw_chars & set(searchable)
                    if len(overlap) / len(kw_chars) >= 0.5:
                        partial_hits += 1
            score = partial_hits / len(keywords) * 0.5  # Lower weight for partial

        combined = score
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
