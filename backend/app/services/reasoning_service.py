"""Reasoning-based retrieval service — true reasoning logic for document queries."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.services.llm import llm_service
from app.services.doc_matcher import match_documents, MatchResult
from app.services.knowledge_graph import knowledge_graph_service

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""
    step_type: str  # "question_analysis", "concept_extraction", "knowledge_retrieval", "logical_inference", "evidence_synthesis"
    description: str
    result: Any
    confidence: float = 0.0


@dataclass
class ReasoningResult:
    """Result of reasoning-based retrieval."""
    query: str
    reasoning_steps: List[ReasoningStep]
    relevant_document_ids: List[str]
    relevant_page_ranges: List[Dict[str, Any]]  # [{doc_id, page_start, page_end, reason}]
    synthesized_answer_hint: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ReasoningRetrievalService:
    """True reasoning-based retrieval service."""
    
    def __init__(self):
        self.kg_service = knowledge_graph_service
    
    async def reason_about_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
        db_session = None
    ) -> ReasoningResult:
        """
        Perform multi-step reasoning to understand and retrieve relevant document content.
        
        Steps:
        1. Query analysis and intent refinement
        2. Concept extraction and expansion
        3. Knowledge graph retrieval
        4. Logical inference and hypothesis generation
        5. Evidence synthesis and ranking
        """
        reasoning_steps = []
        
        # Step 1: Query analysis
        analysis_step = await self._analyze_query(query, conversation_history)
        reasoning_steps.append(analysis_step)
        
        # Step 2: Concept extraction
        concept_step = await self._extract_concepts(query, analysis_step.result)
        reasoning_steps.append(concept_step)
        
        # Step 3: Knowledge graph retrieval
        kg_step = await self._retrieve_knowledge(concept_step.result, user_id, db_session)
        reasoning_steps.append(kg_step)
        
        # Step 4: Logical inference
        inference_step = await self._make_inferences(query, analysis_step.result, kg_step.result)
        reasoning_steps.append(inference_step)
        
        # Step 5: Evidence synthesis
        synthesis_step = await self._synthesize_evidence(
            query, 
            analysis_step.result, 
            kg_step.result, 
            inference_step.result
        )
        reasoning_steps.append(synthesis_step)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(reasoning_steps)
        
        return ReasoningResult(
            query=query,
            reasoning_steps=reasoning_steps,
            relevant_document_ids=synthesis_step.result.get("document_ids", []),
            relevant_page_ranges=synthesis_step.result.get("page_ranges", []),
            synthesized_answer_hint=synthesis_step.result.get("answer_hint"),
            confidence=confidence,
            metadata={
                "analysis": analysis_step.result,
                "concepts": concept_step.result,
                "inferences": inference_step.result
            }
        )
    
    async def _analyze_query(
        self, 
        query: str, 
        history: Optional[List[Dict]]
    ) -> ReasoningStep:
        """Analyze query for deeper understanding beyond simple intent."""
        prompt = f"""Analyze this query for a document Q&A system:

Query: {query}
History: {json.dumps(history[-5:]) if history else "None"}

Please analyze:
1. What is the user really asking? (underlying need)
2. What type of answer would satisfy them? (factual, explanatory, comparative, etc.)
3. What assumptions might the user have?
4. What would a complete answer need to address?

Respond in JSON:
{{
  "underlying_need": "...",
  "answer_type": "factual|explanatory|comparative|procedural|evaluative",
  "assumptions": ["..."],
  "required_components": ["..."],
  "complexity_level": "simple|moderate|complex"
}}"""
        
        try:
            response = await self._call_llm(prompt)
            analysis = json.loads(response)
            return ReasoningStep(
                step_type="question_analysis",
                description="Deep analysis of user query",
                result=analysis,
                confidence=0.85
            )
        except Exception as e:
            logger.warning(f"Query analysis failed: {e}")
            return ReasoningStep(
                step_type="question_analysis",
                description="Fallback analysis",
                result={
                    "underlying_need": "Find relevant document information",
                    "answer_type": "factual",
                    "assumptions": [],
                    "required_components": ["relevant_documents"],
                    "complexity_level": "simple"
                },
                confidence=0.5
            )
    
    async def _extract_concepts(
        self, 
        query: str, 
        analysis: Dict
    ) -> ReasoningStep:
        """Extract and expand concepts from query."""
        prompt = f"""Extract and expand concepts from this query:

Query: {query}
Analysis: {json.dumps(analysis, ensure_ascii=False)}

Extract:
1. Core entities (people, organizations, products, etc.)
2. Key concepts/ideas
3. Related terms (synonyms, hyponyms, hypernyms)
4. Contextual expansions (what else might be relevant)

Respond in JSON:
{{
  "core_entities": ["..."],
  "key_concepts": ["..."],
  "related_terms": ["..."],
  "contextual_expansions": ["..."],
  "concept_relationships": [{{"from": "...", "to": "...", "relation": "..."}}]
}}"""
        
        try:
            response = await self._call_llm(prompt)
            concepts = json.loads(response)
            
            # Enhance with knowledge graph if available
            enhanced_concepts = await self._enhance_with_kg(concepts)
            
            return ReasoningStep(
                step_type="concept_extraction",
                description="Extract and expand concepts",
                result=enhanced_concepts,
                confidence=0.8
            )
        except Exception as e:
            logger.warning(f"Concept extraction failed: {e}")
            return ReasoningStep(
                step_type="concept_extraction",
                description="Fallback concept extraction",
                result={
                    "core_entities": [],
                    "key_concepts": re.findall(r'\b\w{3,}\b', query.lower()),
                    "related_terms": [],
                    "contextual_expansions": [],
                    "concept_relationships": []
                },
                confidence=0.4
            )
    
    async def _retrieve_knowledge(
        self, 
        concepts: Dict, 
        user_id: Optional[str], 
        db_session
    ) -> ReasoningStep:
        """Retrieve knowledge from graph and documents."""
        # Get concepts for retrieval
        all_terms = (
            concepts.get("core_entities", []) + 
            concepts.get("key_concepts", []) + 
            concepts.get("related_terms", [])
        )
        
        # Use knowledge graph
        kg_results = []
        if self.kg_service:
            try:
                kg_results = await self.kg_service.search_concepts(all_terms, user_id)
            except Exception as e:
                logger.warning(f"Knowledge graph search failed: {e}")
        
        # Use document matcher
        doc_results = []
        if db_session and all_terms:
            try:
                doc_results = await match_documents(
                    " ".join(all_terms[:5]),  # Use top concepts
                    all_terms,
                    db_session,
                    user_id
                )
            except Exception as e:
                logger.warning(f"Document matching failed: {e}")
        
        return ReasoningStep(
            step_type="knowledge_retrieval",
            description="Retrieve knowledge from graph and documents",
            result={
                "kg_results": kg_results,
                "doc_results": [r.to_dict() for r in doc_results],
                "search_terms": all_terms
            },
            confidence=0.75 if kg_results or doc_results else 0.3
        )
    
    async def _make_inferences(
        self, 
        query: str, 
        analysis: Dict, 
        knowledge: Dict
    ) -> ReasoningStep:
        """Make logical inferences based on query and retrieved knowledge."""
        prompt = f"""Make logical inferences for this query:

Query: {query}
Analysis: {json.dumps(analysis, ensure_ascii=False)}
Retrieved Knowledge: {json.dumps(knowledge, ensure_ascii=False)}

Generate:
1. Hypotheses about what the answer might contain
2. Logical connections between concepts
3. Missing information that would be helpful
4. Potential contradictions or ambiguities

Respond in JSON:
{{
  "hypotheses": ["..."],
  "logical_connections": [{{"from": "...", "to": "...", "connection": "..."}}],
  "missing_information": ["..."],
  "ambiguities": ["..."],
  "inference_confidence": 0.0-1.0
}}"""
        
        try:
            response = await self._call_llm(prompt)
            inferences = json.loads(response)
            return ReasoningStep(
                step_type="logical_inference",
                description="Make logical inferences",
                result=inferences,
                confidence=float(inferences.get("inference_confidence", 0.6))
            )
        except Exception as e:
            logger.warning(f"Inference generation failed: {e}")
            return ReasoningStep(
                step_type="logical_inference",
                description="Fallback inference",
                result={
                    "hypotheses": [f"The answer relates to {query}"],
                    "logical_connections": [],
                    "missing_information": [],
                    "ambiguities": [],
                    "inference_confidence": 0.4
                },
                confidence=0.4
            )
    
    async def _synthesize_evidence(
        self, 
        query: str, 
        analysis: Dict, 
        knowledge: Dict, 
        inferences: Dict
    ) -> ReasoningStep:
        """Synthesize evidence and rank relevance."""
        prompt = f"""Synthesize evidence for answering this query:

Query: {query}
Analysis: {json.dumps(analysis, ensure_ascii=False)}
Knowledge: {json.dumps(knowledge, ensure_ascii=False)}
Inferences: {json.dumps(inferences, ensure_ascii=False)}

Synthesize:
1. Which documents are most relevant and why?
2. What page ranges should be examined?
3. What would a good answer need to include?
4. Confidence in current evidence

Respond in JSON:
{{
  "document_ids": ["..."],
  "page_ranges": [
    {{"doc_id": "...", "page_start": 1, "page_end": 5, "reason": "..."}}
  ],
  "answer_hint": "...",
  "evidence_quality": "high|medium|low",
  "synthesis_confidence": 0.0-1.0
}}"""
        
        try:
            response = await self._call_llm(prompt)
            synthesis = json.loads(response)
            
            # Enhance with actual document matching results
            doc_results = knowledge.get("doc_results", [])
            if doc_results:
                # Use actual document IDs from matching
                actual_doc_ids = [r["document_id"] for r in doc_results[:3]]
                synthesis["document_ids"] = list(set(synthesis.get("document_ids", []) + actual_doc_ids))
            
            return ReasoningStep(
                step_type="evidence_synthesis",
                description="Synthesize and rank evidence",
                result=synthesis,
                confidence=float(synthesis.get("synthesis_confidence", 0.7))
            )
        except Exception as e:
            logger.warning(f"Evidence synthesis failed: {e}")
            return ReasoningStep(
                step_type="evidence_synthesis",
                description="Fallback synthesis",
                result={
                    "document_ids": [],
                    "page_ranges": [],
                    "answer_hint": "Check relevant documents for information",
                    "evidence_quality": "low",
                    "synthesis_confidence": 0.3
                },
                confidence=0.3
            )
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with timeout."""
        try:
            parts = []
            async for chunk in llm_service.generate(prompt, "", stream=False):
                parts.append(chunk)
            return "".join(parts).strip()
        except asyncio.TimeoutError:
            raise TimeoutError("LLM call timed out")
    
    async def _enhance_with_kg(self, concepts: Dict) -> Dict:
        """Enhance concepts with knowledge graph if available."""
        if not self.kg_service:
            return concepts
        
        enhanced = concepts.copy()
        all_terms = (
            concepts.get("core_entities", []) + 
            concepts.get("key_concepts", []) + 
            concepts.get("related_terms", [])
        )
        
        try:
            for term in all_terms[:10]:  # Limit to top terms
                related = await self.kg_service.get_related_concepts(term)
                if related:
                    enhanced.setdefault("kg_enhancements", {})[term] = related
        except Exception as e:
            logger.debug(f"KG enhancement failed: {e}")
        
        return enhanced
    
    def _calculate_confidence(self, steps: List[ReasoningStep]) -> float:
        """Calculate overall confidence from reasoning steps."""
        if not steps:
            return 0.3
        
        # Weight later steps more heavily (synthesis is most important)
        weights = {
            "question_analysis": 0.15,
            "concept_extraction": 0.15,
            "knowledge_retrieval": 0.2,
            "logical_inference": 0.2,
            "evidence_synthesis": 0.3
        }
        
        total_weight = 0
        weighted_sum = 0
        
        for step in steps:
            weight = weights.get(step.step_type, 0.1)
            total_weight += weight
            weighted_sum += step.confidence * weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.5


# Singleton instance
reasoning_service = ReasoningRetrievalService()