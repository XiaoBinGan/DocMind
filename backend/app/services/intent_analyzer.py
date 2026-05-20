"""Intent analyzer — match user messages to registered APIs or chains."""

import json
import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import ApiDefinition, SerialChain, SerialChainMember
from app.models.schemas import IntentSuggestion


def analyze_intent(user_message: str, keyword: str = "") -> list[IntentSuggestion]:
    """Analyze user intent and return top suggestions.
    
    Uses keyword matching, method hints, and keyword overlap scoring.
    """
    if not keyword:
        return []
    
    suggestions: list[IntentSuggestion] = []
    
    # Keyword matching
    for api_keyword in keyword:
        score = _match_score(user_message, api_keyword)
        if score > 0.3:
            suggestions.append(IntentSuggestion(
                type="api",
                confidence=min(score, 1.0),
                target_name=api_keyword,
                explanation=f"User query '{user_message}' matches API keyword '{api_keyword}'",
                example_queries=[],
            ))
    
    # Sort by confidence
    suggestions.sort(key=lambda x: x.confidence, reverse=True)
    return suggestions[:5]  # Top 5


def _match_score(message: str, keyword: str) -> float:
    """Calculate match score between message and keyword."""
    msg_lower = message.lower()
    kw_lower = keyword.lower()
    
    if kw_lower in msg_lower:
        return 0.9
    
    # Check word overlap
    msg_words = set(re.findall(r'\w+', msg_lower))
    kw_words = set(re.findall(r'\w+', kw_lower))
    
    if not kw_words:
        return 0
    
    overlap = len(msg_words & kw_words) / len(kw_words)
    return overlap * 0.8


def analyze_intent_for_chain(chain: SerialChain, users_message: str) -> IntentSuggestion:
    """Analyze if user wants to execute a chain."""
    chain_name_lower = chain.name.lower()
    msg_lower = users_message.lower()
    
    if chain_name_lower in msg_lower:
        return IntentSuggestion(
            type="chain",
            confidence=0.85,
            target_id=chain.id,
            target_name=chain.name,
            explanation=f"User message contains chain name '{chain.name}'",
        )
    
    # Check member API names
    score = 0
    for member in chain.members or []:
        if member.api and member.api.name.lower() in msg_lower:
            score += 0.5
    if score > 0:
        return IntentSuggestion(
            type="chain",
            confidence=min(score, 0.9),
            target_id=chain.id,
            target_name=chain.name,
            explanation=f"User message matches {score} API(s) in chain '{chain.name}'",
        )
    
    return IntentSuggestion(type="chain", confidence=0, target_name=chain.name, explanation="")
