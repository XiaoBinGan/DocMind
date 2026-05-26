"""Plan-and-Execute Agent — replaces single-shot LLM selection with structured reasoning.

P2 升级：解决"假推理式检索"问题。
- Planner：分析问题，生成执行计划（分解为独立步骤）
- Executor：逐步执行计划，调用检索/推理工具
- Verifier：每步校验结果，决定是否调整计划或继续
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Callable, Awaitable

from app.services.llm import llm_service
from app.services.doc_matcher import match_documents
from app.services.knowledge_graph import knowledge_graph_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY = "retry"


class StepType(str, Enum):
    SEARCH = "search"          # Retrieve content from documents
    COMPARE = "compare"        # Compare multiple findings
    ANALYZE = "analyze"        # Deep analysis of retrieved content
    SYNTHESIZE = "synthesize"  # Synthesize evidence into answer
    VERIFY = "verify"          # Verify an intermediate result
    CLARIFY = "clarify"        # Ask user for clarification


@dataclass
class ExecutionStep:
    """A single step in the execution plan."""
    step_id: int
    step_type: StepType
    description: str
    dependencies: List[int] = field(default_factory=list)  # step_ids this depends on
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    retry_count: int = 0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """A complete execution plan for answering a query."""
    plan_id: str
    query: str
    steps: List[ExecutionStep]
    estimated_total_steps: int = 0
    current_step: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def pending_steps(self) -> List[ExecutionStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (StepStatus.VERIFIED, StepStatus.SKIPPED)
            for s in self.steps
        )

    def get_next_step(self) -> Optional[ExecutionStep]:
        """Get the next step whose dependencies are all VERIFIED."""
        verified_ids = {s.step_id for s in self.steps if s.status == StepStatus.VERIFIED}
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if all(dep in verified_ids for dep in step.dependencies):
                    return step
        return None


@dataclass
class PlanResult:
    """Final result of plan execution."""
    query: str
    plan: ExecutionPlan
    final_answer: str
    confidence: float
    total_elapsed_ms: float
    steps_executed: int
    evidence_chain: List[Dict[str, Any]]


# ──────────────────────────────────────────────────────────────
# Planner
# ──────────────────────────────────────────────────────────────

_PLANNER_PROMPT = """You are a reasoning planner for a document Q&A system. Given a user question,
create a step-by-step execution plan to answer it thoroughly.

Available step types and their tools:
- "search": Retrieve content from documents (uses document index + entity index)
- "compare": Compare multiple findings or documents
- "analyze": Deep analysis of retrieved content for patterns, contradictions, or implications
- "synthesize": Synthesize evidence from previous steps into a coherent answer
- "verify": Verify an intermediate result against source documents

Rules:
1. First step MUST be "search" to retrieve relevant content
2. Steps must have clear dependencies (later steps depend on earlier steps)
3. Maximum 7 steps
4. Steps should be atomic and self-contained
5. Include a final "synthesize" step to produce the answer
6. Output ONLY a JSON array, no other text

User question: {query}

JSON execution plan:"""


class Planner:
    """Generate execution plans from user queries via LLM."""

    async def create_plan(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> ExecutionPlan:
        """Create an execution plan for answering a query.

        Args:
            query: User's question
            conversation_history: Optional conversation context

        Returns:
            ExecutionPlan with ordered, dependent steps.
        """
        prompt = _PLANNER_PROMPT.format(query=query)

        try:
            raw = await llm_service.generate(prompt)
            steps_data = self._parse_steps(raw)

            if not steps_data:
                # Fallback: default plan structure
                steps_data = [
                    {"step_type": "search", "description": f"检索与'{query}'相关的内容", "dependencies": []},
                    {"step_type": "analyze", "description": "分析检索结果", "dependencies": [0]},
                    {"step_type": "synthesize", "description": "综合生成答案", "dependencies": [1]},
                ]

            steps = []
            for i, sd in enumerate(steps_data):
                step_type = StepType(sd.get("step_type", "search"))
                steps.append(ExecutionStep(
                    step_id=i,
                    step_type=step_type,
                    description=sd.get("description", f"Step {i}"),
                    dependencies=sd.get("dependencies", []),
                ))

            plan_id = f"plan_{int(time.time())}_{hash(query) % 10000:04d}"
            return ExecutionPlan(
                plan_id=plan_id,
                query=query,
                steps=steps,
                estimated_total_steps=len(steps),
            )

        except Exception as exc:
            logger.error("Plan creation failed: %s", exc)
            raise

    def _parse_steps(self, raw: str) -> List[Dict]:
        """Parse LLM output into steps list."""
        # Try direct JSON parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try markdown code block
        code_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any JSON array
        arr_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if arr_match:
            try:
                return json.loads(arr_match.group())
            except json.JSONDecodeError:
                pass

        return []


# ──────────────────────────────────────────────────────────────
# Executor
# ──────────────────────────────────────────────────────────────

class Executor:
    """Execute individual steps of the plan using available tools.

    Maps step types to concrete actions:
    - search → document retrieval (via doc_matcher + entity_indexer)
    - compare → LLM-powered comparison of retrieved results
    - analyze → LLM-powered deep analysis
    - synthesize → LLM-powered evidence synthesis
    - verify → Verification against source content
    """

    def __init__(self, retrieve_fn=None):
        """
        Args:
            retrieve_fn: Optional async callable (query, top_k) -> list of chunks.
                         If not provided, falls back to doc_matcher.
        """
        self._retrieve_fn = retrieve_fn

    async def execute_step(
        self,
        step: ExecutionStep,
        previous_results: Dict[int, str],
        user_id: Optional[str] = None,
        db_session=None,
    ) -> str:
        """Execute a single step and return its result.

        Args:
            step: The step to execute
            previous_results: Map of step_id -> result from completed steps
            user_id: Optional user identifier
            db_session: Optional database session

        Returns:
            The result string from executing the step.
        """
        start = time.time()
        step.status = StepStatus.EXECUTING

        try:
            result = await self._dispatch(step, previous_results, user_id, db_session)
            step.result = result
            step.elapsed_ms = (time.time() - start) * 1000
            return result
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.elapsed_ms = (time.time() - start) * 1000
            logger.error("Step %d failed: %s", step.step_id, exc)
            raise

    async def _dispatch(
        self,
        step: ExecutionStep,
        previous_results: Dict[int, str],
        user_id: Optional[str],
        db_session,
    ) -> str:
        """Dispatch step to the appropriate handler."""
        if step.step_type == StepType.SEARCH:
            return await self._execute_search(step, previous_results)
        elif step.step_type == StepType.COMPARE:
            return await self._execute_compare(step, previous_results)
        elif step.step_type == StepType.ANALYZE:
            return await self._execute_analyze(step, previous_results)
        elif step.step_type == StepType.SYNTHESIZE:
            return await self._execute_synthesize(step, previous_results)
        elif step.step_type == StepType.VERIFY:
            return await self._execute_verify(step, previous_results)
        else:
            raise ValueError(f"Unknown step type: {step.step_type}")

    async def _execute_search(
        self, step: ExecutionStep, previous_results: Dict[int, str]
    ) -> str:
        """Execute a search step: retrieve document content.

        Uses the injected retrieve_fn if available, otherwise falls back
        to the doc_matcher module.
        """
        query = step.description
        if self._retrieve_fn:
            results = await self._retrieve_fn(query, top_k=10)
        else:
            match_results = await match_documents(query, top_k=10)
            results = [
                {"page": mr.page_start, "content": mr.snippet, "score": mr.score}
                for mr in match_results
            ] if match_results else []

        if not results:
            return "NO_RESULTS: 未找到与查询相关的文档内容。"

        return json.dumps(results, ensure_ascii=False, indent=2)

    async def _execute_compare(
        self, step: ExecutionStep, previous_results: Dict[int, str]
    ) -> str:
        """Execute a compare step: LLM-powered comparison."""
        context = "\n".join(
            f"Step {sid}: {res[:500]}"
            for sid, res in previous_results.items()
            if sid in step.dependencies
        )
        prompt = f"""Compare the following search results and identify key similarities and differences.

Search results:
{context}

Comparison focus: {step.description}

Respond with a concise comparison analysis:"""

        return await llm_service.generate(prompt)

    async def _execute_analyze(
        self, step: ExecutionStep, previous_results: Dict[int, str]
    ) -> str:
        """Execute an analyze step: deep LLM analysis."""
        context = "\n".join(
            f"Step {sid}: {res[:800]}"
            for sid, res in previous_results.items()
            if sid in step.dependencies
        )
        prompt = f"""Analyze the following document content deeply.

Content:
{context}

Analysis task: {step.description}

Identify: key facts, patterns, potential gaps, and logical connections.
Respond with a structured analysis:"""

        return await llm_service.generate(prompt)

    async def _execute_synthesize(
        self, step: ExecutionStep, previous_results: Dict[int, str]
    ) -> str:
        """Execute a synthesize step: combine evidence into final answer."""
        all_evidence = "\n\n".join(
            f"--- Step {sid} Result ---\n{res}"
            for sid, res in previous_results.items()
        )

        prompt = f"""Synthesize a comprehensive answer based on all the evidence below.

Original question: {step.description}

Evidence from previous steps:
{all_evidence}

Rules:
1. Base your answer ONLY on the provided evidence
2. Cite specific document content when possible
3. If evidence is insufficient, clearly state what is missing
4. Structure your answer logically

Synthesized answer:"""

        return await llm_service.generate(prompt)

    async def _execute_verify(
        self, step: ExecutionStep, previous_results: Dict[int, str]
    ) -> str:
        """Execute a verify step: check result against sources."""
        target_step_id = step.dependencies[0] if step.dependencies else -1
        result_to_verify = previous_results.get(target_step_id, "")
        source_context = ""

        # Find the earliest search result as ground truth
        for sid, res in sorted(previous_results.items()):
            if "search" in str(sid).lower() or sid != target_step_id:
                source_context = res[:1000]
                break

        prompt = f"""Verify whether the following result is supported by the source content.

Result to verify:
{result_to_verify[:1000]}

Source content:
{source_context[:1000]}

Respond with JSON:
{{"verified": true/false, "confidence": 0.0-1.0, "issues": ["..."], "correction": "..."}}"""

        return await llm_service.generate(prompt)


# ──────────────────────────────────────────────────────────────
# Verifier
# ──────────────────────────────────────────────────────────────

class Verifier:
    """Verify each step's result and decide next action.

    Decision outcomes:
    - PROCEED: Result is good, move to next step
    - RETRY: Result is poor but recoverable, retry with adjusted parameters
    - FALLBACK: Multiple retries failed, use simpler fallback approach
    - ABORT: Cannot continue, return partial results
    """

    class Verdict(str, Enum):
        PROCEED = "proceed"
        RETRY = "retry"
        FALLBACK = "fallback"
        ABORT = "abort"

    async def verify(
        self,
        step: ExecutionStep,
        plan: ExecutionPlan,
        previous_results: Dict[int, str],
        original_query: str,
    ) -> Verdict:
        """Verify a step's result and decide next action.

        Args:
            step: The step that was just executed
            plan: The current execution plan
            previous_results: Results from all completed steps
            original_query: The original user query

        Returns:
            Verdict indicating next action.
        """
        # Pre-checks without LLM

        # Empty result or NO_RESULTS → RETRY once
        if not step.result or step.result.startswith("NO_RESULTS"):
            if step.retry_count < step.max_retries:
                return self.Verdict.RETRY
            return self.Verdict.FALLBACK

        # Very short result for non-search steps → suspicious
        if step.step_type != StepType.SEARCH and len(step.result or "") < 50:
            if step.retry_count < step.max_retries:
                return self.Verdict.RETRY
            return self.Verdict.PROCEED  # Accept short result after retries

        # LLM-powered verification for critical steps
        if step.step_type in (StepType.SYNTHESIZE, StepType.ANALYZE):
            try:
                verification = await self._llm_verify(step, previous_results, original_query)
                confidence = verification.get("confidence", 0.5)

                if confidence >= 0.7:
                    step.confidence = confidence
                    return self.Verdict.PROCEED
                elif confidence >= 0.4:
                    if step.retry_count < step.max_retries:
                        step.confidence = confidence
                        return self.Verdict.RETRY
                    return self.Verdict.PROCEED  # Accept after retries
                else:
                    return self.Verdict.FALLBACK

            except Exception:
                pass  # LLM verification failed, proceed optimistically

        # Default: proceed
        return self.Verdict.PROCEED

    async def _llm_verify(
        self,
        step: ExecutionStep,
        previous_results: Dict[int, str],
        original_query: str,
    ) -> Dict[str, Any]:
        """Use LLM to verify a step's quality."""
        prompt = f"""Evaluate the quality of this intermediate result.

Original question: {original_query}
Step type: {step.step_type}
Step description: {step.description}
Step result: {(step.result or '')[:1500]}

Rate on:
- Relevance: Does this address the step goal?
- Completeness: Is the result thorough enough?
- Accuracy: Does it align with known facts?

Respond with JSON:
{{"confidence": 0.0-1.0, "relevance_score": 0.0-1.0, "completeness_score": 0.0-1.0, "issues": ["..."]}}"""

        raw = await llm_service.generate(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"confidence": 0.5}


# ──────────────────────────────────────────────────────────────
# Plan-and-Execute Agent (orchestrator)
# ──────────────────────────────────────────────────────────────

class PlanExecuteAgent:
    """Orchestrates the Plan-and-Execute loop.

    Full pipeline:
    1. Planner generates execution plan
    2. Executor runs each step
    3. Verifier checks each step → PROCEED / RETRY / FALLBACK / ABORT
    4. Loop until plan complete or aborted
    """

    def __init__(
        self,
        retrieve_fn: Optional[Callable[..., Awaitable[List[Dict]]]] = None,
    ):
        self.planner = Planner()
        self.executor = Executor(retrieve_fn=retrieve_fn)
        self.verifier = Verifier()
        self.max_total_steps = 10

    async def execute(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
        db_session=None,
    ) -> PlanResult:
        """Execute the full Plan-and-Execute pipeline.

        Args:
            query: User's question
            conversation_history: Optional conversation context
            user_id: Optional user identifier
            db_session: Optional database session

        Returns:
            PlanResult with final answer, plan, and execution metadata.
        """
        overall_start = time.time()

        # Phase 1: Plan
        plan = await self.planner.create_plan(query, conversation_history)

        # Phase 2-3: Execute + Verify loop
        previous_results: Dict[int, str] = {}
        evidence_chain: List[Dict[str, Any]] = []
        steps_executed = 0

        while not plan.is_complete and steps_executed < self.max_total_steps:
            next_step = plan.get_next_step()
            if next_step is None:
                # All pending steps have unresolved dependencies → abort
                logger.warning("Deadlock: no step with resolved dependencies")
                break

            steps_executed += 1

            # Execute
            try:
                result = await self.executor.execute_step(
                    next_step, previous_results, user_id, db_session
                )
                previous_results[next_step.step_id] = result
            except Exception as exc:
                logger.error("Step %d execution error: %s", next_step.step_id, exc)
                next_step.status = StepStatus.FAILED
                evidence_chain.append({
                    "step_id": next_step.step_id,
                    "status": "failed",
                    "error": str(exc),
                })
                continue

            # Verify
            verdict = await self.verifier.verify(
                next_step, plan, previous_results, query
            )

            if verdict == Verifier.Verdict.PROCEED:
                next_step.status = StepStatus.VERIFIED
                evidence_chain.append({
                    "step_id": next_step.step_id,
                    "step_type": next_step.step_type.value,
                    "status": "verified",
                    "confidence": next_step.confidence,
                    "result_snippet": (next_step.result or "")[:200],
                })

            elif verdict == Verifier.Verdict.RETRY:
                next_step.retry_count += 1
                next_step.status = StepStatus.RETRY
                continue  # Loop will pick up this step again

            elif verdict == Verifier.Verdict.FALLBACK:
                next_step.status = StepStatus.VERIFIED  # Accept as-is
                evidence_chain.append({
                    "step_id": next_step.step_id,
                    "step_type": next_step.step_type.value,
                    "status": "fallback",
                    "result_snippet": (next_step.result or "")[:200],
                })

            elif verdict == Verifier.Verdict.ABORT:
                logger.warning("Plan aborted at step %d", next_step.step_id)
                break

        # Extract final answer (last SYNTHESIZE step result)
        final_answer = ""
        final_confidence = 0.5
        for step in reversed(plan.steps):
            if step.step_type == StepType.SYNTHESIZE and step.result:
                final_answer = step.result
                final_confidence = step.confidence
                break

        if not final_answer:
            # Fallback: concatenate all verified results
            verified_results = [
                step.result for step in plan.steps
                if step.status == StepStatus.VERIFIED and step.result
            ]
            final_answer = "\n\n".join(verified_results) if verified_results else "抱歉，无法在当前文档中找到相关信息。"

        total_ms = (time.time() - overall_start) * 1000

        return PlanResult(
            query=query,
            plan=plan,
            final_answer=final_answer,
            confidence=final_confidence,
            total_elapsed_ms=total_ms,
            steps_executed=steps_executed,
            evidence_chain=evidence_chain,
        )


# ──────────────────────────────────────────────────────────────
# Convenience: drop-in replacement for reasoning_service
# ──────────────────────────────────────────────────────────────

async def plan_and_execute(
    query: str,
    retrieve_fn: Optional[Callable] = None,
    conversation_history: Optional[List[Dict]] = None,
    user_id: Optional[str] = None,
    db_session=None,
) -> PlanResult:
    """One-shot plan-and-execute, designed as drop-in for reasoning_service.

    Usage (in chat.py):
        result = await plan_and_execute(
            query=user_message,
            retrieve_fn=page_retriever.retrieve,
            conversation_history=history,
            user_id=user_id,
            db_session=db,
        )
        final_answer = result.final_answer
    """
    agent = PlanExecuteAgent(retrieve_fn=retrieve_fn)
    return await agent.execute(
        query=query,
        conversation_history=conversation_history,
        user_id=user_id,
        db_session=db_session,
    )


# ──────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────

plan_execute_agent = PlanExecuteAgent()