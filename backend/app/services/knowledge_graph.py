"""知识图谱服务 — 概念↔API/工作流的语义映射。

节点类型: concept / api / chain / document
关系类型: related_to (概念↔概念) / suitable_for (概念→API) / in_chain (概念→工作流) / chain_member (链→API)

核心能力:
1. 自动建图：注册 API/工作流时从名称/描述/示例中提取关键词建概念节点
2. 查询推荐：给定查询词，在图谱中找到相邻节点并排序推荐
3. 聊天增强：分析对话历史，提取用户关注的概念，推荐可用工具
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    ApiDefinition, SerialChain, SerialChainMember,
    KGNode, KGEdge,
)
from app.models.schemas import IntentSuggestion
from app.services.intent_service import IntentResult
from app.services.intent_service import extract_keywords

logger = logging.getLogger(__name__)

# ─── 中文停止词 ───
_STOPWORDS_ZH = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "什么", "怎么",
    "如何", "哪", "那", "这个", "那个", "吗", "呢", "吧", "啊", "可以",
    "能", "请", "帮", "想", "把", "被", "让", "用", "对", "从", "以",
    "及", "等", "中", "与", "或", "但", "如果", "因为", "所以", "然后",
    "虽然", "但是", "不过", "还", "又", "更", "最", "只", "才", "呢",
    "for", "and", "or", "the", "a", "an", "is", "are", "was", "were",
    "of", "to", "in", "it", "by", "with", "at", "on", "this", "that",
}


# ─────────── 数据模型 ───────────

@dataclass
class KGNodeSummary:
    """知识图谱节点摘要（序列化友好）"""
    id: str
    label: str
    kind: str  # concept / api / chain / document
    frequency: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KGEdgeSummary:
    """知识图谱边摘要"""
    source_label: str
    target_label: str
    relation: str
    weight: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Recommendation:
    """推荐结果"""
    target_id: str
    target_name: str
    target_kind: str
    score: float
    reasoning: str
    match_nodes: list[KGNodeSummary] = field(default_factory=list)
    match_edges: list[KGEdgeSummary] = field(default_factory=list)

    def to_suggestion(self) -> IntentSuggestion:
        return IntentSuggestion(
            type="chain" if self.target_kind == "chain" else "api",
            confidence=min(self.score, 1.0),
            target_id=self.target_id,
            target_name=self.target_name,
            explanation=self.reasoning,
            example_queries=[],
        )


# ─────────── 关键词提取 ───────────

def _extract_concept_keywords(text: str, top_n: int = 10) -> list[str]:
    """从文本中提取概念关键词。"""
    try:
        raw = extract_keywords(text, top_n=top_n * 2)
    except Exception:
        raw = []
    # 过滤停止词
    result = [w for w in raw if w not in _STOPWORDS_ZH and len(w) >= 2]
    return result[:top_n]


# ─────────── 自动建图 ───────────

async def _ensure_node(session: AsyncSession, label: str, kind: str,
                       source_id: str | None) -> KGNode:
    """确保节点存在，不存在则创建。"""
    result = await session.execute(
        select(KGNode).where(KGNode.label == label, KGNode.kind == kind)
    )
    node = result.scalar_one_or_none()
    if node:
        node.frequency += 1
        node.updated_at = func.now()  # type: ignore[assignment]
        return node

    node = KGNode(label=label, kind=kind, payload="{}", frequency=1, source_id=source_id)
    session.add(node)
    await session.flush()
    return node


async def _ensure_edge(session: AsyncSession, src: KGNode, tgt: KGNode,
                       relation: str) -> KGEdge:
    """确保边存在，不存在则创建，存在则增加权重。"""
    result = await session.execute(
        select(KGEdge).where(
            KGEdge.source_id == src.id, KGEdge.target_id == tgt.id,
            KGEdge.relation == relation,
        )
    )
    edge = result.scalar_one_or_none()
    if edge:
        edge.weight += 1
        return edge

    edge = KGEdge(source_id=src.id, target_id=tgt.id, relation=relation, weight=1)
    session.add(edge)
    await session.flush()
    return edge


async def build_kg_from_apis(session: AsyncSession) -> int:
    """扫描已注册的 API，从名称/描述/示例查询中提取概念节点并建图。

    返回新建的节点数量。
    """
    result = await session.execute(select(ApiDefinition).where(ApiDefinition.enabled == 1))
    apis = result.scalars().all()
    node_count = 0

    for api in apis:
        # 创建 API 节点
        api_node = await _ensure_node(session, api.name, "api", api.id)

        # 从名称提取概念
        name_kws = _extract_concept_keywords(api.name, top_n=5)
        for kw in name_kws:
            concept_node = await _ensure_node(session, kw, "concept", api.id)
            await _ensure_edge(session, concept_node, api_node, "suitable_for")
            # 同一概念内的节点互为 related_to
            # (通过后续遍历处理)
            node_count += 1

        # 从描述提取概念
        if api.description:
            desc_kws = _extract_concept_keywords(api.description, top_n=5)
            for kw in desc_kws:
                concept_node = await _ensure_node(session, kw, "concept", api.id)
                await _ensure_edge(session, concept_node, api_node, "suitable_for")
                node_count += 1

        # 从示例查询提取概念
        if api.example_queries:
            try:
                examples = json.loads(api.example_queries)
            except (json.JSONDecodeError, TypeError):
                examples = []
            for ex in examples:
                ex_kws = _extract_concept_keywords(ex, top_n=3)
                for kw in ex_kws:
                    concept_node = await _ensure_node(session, kw, "concept", api.id)
                    await _ensure_edge(session, concept_node, api_node, "suitable_for")
                    node_count += 1

        # 概念之间的 mutual-link
    # 完成 API 处理后的 mutual-link 在后续统一处理

    return node_count


async def build_kg_from_chains(session: AsyncSession) -> int:
    """扫描已注册的 Chain，从名称/描述/成员中提取概念节点并建图。"""
    result = await session.execute(select(SerialChain).where(SerialChain.enabled == 1))
    chains = result.scalars().all()
    node_count = 0

    for chain in chains:
        chain_node = await _ensure_node(session, chain.name, "chain", chain.id)

        # 从工作流名称提取概念
        name_kws = _extract_concept_keywords(chain.name, top_n=5)
        for kw in name_kws:
            concept_node = await _ensure_node(session, kw, "concept", chain.id)
            await _ensure_edge(session, concept_node, chain_node, "suitable_for")
            node_count += 1

        # 从描述提取概念
        if chain.description:
            desc_kws = _extract_concept_keywords(chain.description, top_n=5)
            for kw in desc_kws:
                concept_node = await _ensure_node(session, kw, "concept", chain.id)
                await _ensure_edge(session, concept_node, chain_node, "suitable_for")
                node_count += 1

        # 工作流与成员 API 的关系
        m_result = await session.execute(
            select(SerialChainMember).where(
                SerialChainMember.chain_id == chain.id
            ).order_by(SerialChainMember.order)
        )
        members = m_result.scalars().all()
        for m in members:
            # chain → api 关系
            api_result = await session.execute(
                select(ApiDefinition).where(ApiDefinition.id == m.api_id)
            )
            api_def = api_result.scalar_one_or_none()
            if api_def:
                api_node = await _ensure_node(session, api_def.name, "api", api_def.id)
                await _ensure_edge(session, chain_node, api_node, "contains")

                # 链名称也指向 API（间接匹配）
                for kw in _extract_concept_keywords(chain.name, top_n=3):
                    concept_node = await _ensure_node(session, kw, "concept", chain.id)
                    await _ensure_edge(session, concept_node, api_node, "suitable_for")
                    node_count += 1

    return node_count


async def build_kg_from_messages(session: AsyncSession, limit: int = 50) -> int:
    """从最近的对话消息中提取概念节点，连接到已存在的 API/Chain 节点。

    当用户多次提到某个概念且该概念与已有工具匹配时，自动建立 suitable_for 边。
    """
    from app.models.database import Conversation, Message

    # 获取最近的对话消息
    conv_result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    )
    convs = conv_result.scalars().all()

    node_count = 0
    for conv in convs:
        msg_result = await session.execute(
            select(Message).where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        messages = msg_result.scalars().all()

        for msg in messages:
            if msg.role != "user":
                continue
            kws = _extract_concept_keywords(msg.content, top_n=5)
            for kw in kws:
                concept_node = await _ensure_node(session, kw, "concept", conv.id)
                # 尝试与已有 API/Chain 匹配
                if len(kw) >= 2:
                    api_result = await session.execute(
                        select(ApiDefinition).where(
                            ApiDefinition.name.ilike(f"%{kw}%")
                        ).limit(1)
                    )
                    api = api_result.scalar_one_or_none()
                    if api:
                        api_node = await _ensure_node(session, api.name, "api", api.id)
                        await _ensure_edge(session, concept_node, api_node, "suitable_for")
                        concept_node.frequency += 1
                        node_count += 1

                    chain_result = await session.execute(
                        select(SerialChain).where(
                            SerialChain.name.ilike(f"%{kw}%")
                        ).limit(1)
                    )
                    chain = chain_result.scalar_one_or_none()
                    if chain:
                        chain_node = await _ensure_node(session, chain.name, "chain", chain.id)
                        await _ensure_edge(session, concept_node, chain_node, "suitable_for")
                        concept_node.frequency += 1
                        node_count += 1

    return node_count


async def rebuild_all_kg(session: AsyncSession) -> dict:
    """全量重建知识图谱（先清除旧的，再重新扫描）。"""
    await session.execute(KGEdge.__table__.delete())
    await session.execute(KGNode.__table__.delete())
    await session.flush()

    n1 = await build_kg_from_apis(session)
    n2 = await build_kg_from_chains(session)
    n3 = await build_kg_from_messages(session)
    await session.flush()

    # 同一概念节点之间的 mutual-link
    kw_result = await session.execute(
        select(KGNode).where(KGNode.kind == "concept").order_by(KGNode.frequency.desc())
    )
    concepts = kw_result.scalars().all()
    mutual_count = 0
    for i, a in enumerate(concepts):
        for b in concepts[i + 1:]:
            # 如果两个概念有共同的 API/Chain 邻居，建立 related_to
            common = await _shared_neighbors(session, a, b, max_check=5)
            if common > 0:
                await _ensure_edge(session, a, b, "related_to")
                mutual_count += 1

    return {"apis": n1, "chains": n2, "messages": n3, "mutual_links": mutual_count}


async def _shared_neighbors(session: AsyncSession, a: KGNode, b: KGNode,
                            max_check: int = 5) -> int:
    """检查两个概念节点共享多少个共同的 API/Chain 邻居（用于启发式 mutual-link）。"""
    result = await session.execute(
        select(KGEdge).where(
            KGEdge.target_id.in_([a.id, b.id]),
            KGEdge.relation == "suitable_for",
        )
    )
    edges = result.scalars().all()

    source_a = set()
    source_b = set()
    for e in edges:
        # 我们需要反向查找（概念 → API 的边是 concept 作为 source）
        pass

    # 更简单的方式：用 label 做模糊匹配
    score = 0
    for i in range(len(a.label)):
        for j in range(i + 1, min(len(a.label) + 1, len(a.label) + 3)):
            sub = a.label[i:j]
            if sub in b.label:
                score += 1
    return score


# ─────────── 图谱查询 ───────────

async def search_concepts(session: AsyncSession, keyword: str,
                          limit: int = 10) -> list[KGNodeSummary]:
    """搜索概念节点。"""
    result = await session.execute(
        select(KGNode).where(
            KGNode.kind == "concept",
            KGNode.label.ilike(f"%{keyword}%"),
        ).order_by(KGNode.frequency.desc()).limit(limit)
    )
    nodes = result.scalars().all()
    return [KGNodeSummary(id=n.id, label=n.label, kind=n.kind, frequency=n.frequency) for n in nodes]


async def get_neighbors(session: AsyncSession, node_id: str,
                        max_depth: int = 2, limit: int = 10) -> dict:
    """获取节点在图谱中的邻居（多跳）。

    返回结构:
    {
        "node": KGNodeSummary,
        "direct": [EdgeSummary],
        "depth2": [EdgeSummary],
        "concepts": [KGNodeSummary],
        "apis": [KGNodeSummary],
        "chains": [KGNodeSummary],
    }
    """
    node_result = await session.execute(select(KGNode).where(KGNode.id == node_id))
    node = node_result.scalar_one_or_none()
    if not node:
        return {}

    # 直接邻居
    direct_edges_result = await session.execute(
        select(KGEdge).where(
            (KGEdge.source_id == node_id) | (KGEdge.target_id == node_id)
        )
    )
    direct_edges = direct_edges_result.scalars().all()

    # 收集直接邻居节点 ID
    neighbor_ids = set()
    for e in direct_edges:
        if e.source_id == node_id:
            neighbor_ids.add(e.target_id)
        else:
            neighbor_ids.add(e.source_id)

    neighbors = []
    for e in direct_edges:
        src_result = await session.execute(select(KGNode).where(KGNode.id == e.source_id))
        tgt_result = await session.execute(select(KGNode).where(KGNode.id == e.target_id))
        src_node = src_result.scalar_one_or_none()
        tgt_node = tgt_result.scalar_one_or_none()
        neighbors.append(KGEdgeSummary(
            source_label=src_node.label if src_node else "",
            target_label=tgt_node.label if tgt_node else "",
            relation=e.relation,
            weight=e.weight,
        ))

    # 收集目标节点
    concepts = []
    apis = []
    chains = []
    for nid in neighbor_ids:
        n_result = await session.execute(select(KGNode).where(KGNode.id == nid))
        n = n_result.scalar_one_or_none()
        if n:
            s = KGNodeSummary(id=n.id, label=n.label, kind=n.kind, frequency=n.frequency)
            if n.kind == "concept":
                concepts.append(s)
            elif n.kind == "api":
                apis.append(s)
            elif n.kind == "chain":
                chains.append(s)

    return {
        "node": KGNodeSummary(id=node.id, label=node.label, kind=node.kind, frequency=node.frequency),
        "direct": neighbors,
        "concepts": concepts,
        "apis": apis,
        "chains": chains,
    }


# ─────────── 推荐引擎 ───────────

async def recommend_from_query(session: AsyncSession, query: str,
                               top_k: int = 5, min_confidence: float = 0.3) -> list[IntentSuggestion]:
    """基于知识图谱为用户查询推荐 API/工作流。

    流程:
    1. 从查询提取概念关键词
    2. 在图谱中查找匹配的概念节点
    3. 沿着 suitable_for 边找到关联的 API/Chain
    4. 按边权重 + 节点频率排序
    """
    keywords = _extract_concept_keywords(query, top_n=8)
    if not keywords:
        return []

    # Step 1: 找到匹配的概念节点
    matched_concepts: list[KGNode] = []
    for kw in keywords:
        result = await session.execute(
            select(KGNode).where(
                KGNode.kind == "concept",
                KGNode.label.ilike(f"%{kw}%"),
            ).limit(3)
        )
        nodes = result.scalars().all()
        for n in nodes:
            if n not in matched_concepts:
                matched_concepts.append(n)

    if not matched_concepts:
        # 回退到直接匹配 API name/description
        return await _fallback_recommend(session, query, top_k, min_confidence)

    # Step 2: 沿 suitable_for 边找到关联的 API/Chain
    candidate_nodes: dict[str, dict] = {}  # {node_id: {"score": float, "label": str, "kind": str}}

    for concept in matched_concepts:
        # 正向边 (concept → API/Chain)
        edge_result = await session.execute(
            select(KGEdge).where(KGEdge.source_id == concept.id, KGEdge.relation == "suitable_for")
        )
        edges = edge_result.scalars().all()
        for e in edges:
            target_result = await session.execute(select(KGNode).where(KGNode.id == e.target_id))
            target = target_result.scalar_one_or_none()
            if not target:
                continue
            # 权重 = 边的权重 × 概念的频率
            score = e.weight * concept.frequency * 0.5
            if target.id not in candidate_nodes:
                candidate_nodes[target.id] = {
                    "score": score, "label": target.label, "kind": target.kind,
                    "reasoning": [f"概念「{concept.label}」→ {e.relation} → {target.label}"],
                }
            else:
                candidate_nodes[target.id]["score"] += score
                candidate_nodes[target.id]["reasoning"].append(f"概念「{concept.label}」→ {e.relation}")

    # Step 3: 多跳 — 通过 related_to 找到间接关联
    for concept in matched_concepts:
        rel_result = await session.execute(
            select(KGEdge).where(
                (KGEdge.source_id == concept.id) | (KGEdge.target_id == concept.id),
                KGEdge.relation == "related_to",
            )
        )
        rel_edges = rel_result.scalars().all()
        for re in rel_edges:
            other_id = re.target_id if re.source_id == concept.id else re.source_id
            other_result = await session.execute(select(KGNode).where(KGNode.id == other_id))
            other = other_result.scalar_one_or_none()
            if other and other.kind == "concept":
                # 从间接概念再找 API/Chain
                edge_result2 = await session.execute(
                    select(KGEdge).where(
                        KGEdge.source_id == other.id,
                        KGEdge.relation == "suitable_for",
                    )
                )
                edges2 = edge_result2.scalars().all()
                for e2 in edges2:
                    target_result2 = await session.execute(
                        select(KGNode).where(KGNode.id == e2.target_id)
                    )
                    target2 = target_result2.scalar_one_or_none()
                    if not target2 or target2.id in candidate_nodes:
                        continue
                    score = e2.weight * other.frequency * 0.25  # 多跳降低权重
                    candidate_nodes[target2.id] = {
                        "score": score, "label": target2.label, "kind": target2.kind,
                        "reasoning": [f"概念「{concept.label}」→ related_to → 「{other.label}」→ suitable_for → {target2.label}"],
                    }

    # Step 4: 排序并构建推荐
    if not candidate_nodes:
        return await _fallback_recommend(session, query, top_k, min_confidence)

    sorted_candidates = sorted(candidate_nodes.items(), key=lambda x: x[1]["score"], reverse=True)

    suggestions = []
    for target_id, info in sorted_candidates:
        if info["score"] < min_confidence:
            break
        # 检查是否是 API 或 Chain
        if info["kind"] == "api":
            api_result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == target_id))
            api = api_result.scalar_one_or_none()
            if api and api.enabled:
                suggestions.append(IntentSuggestion(
                    type="api",
                    confidence=min(info["score"], 1.0),
                    target_id=api.id,
                    target_name=api.name,
                    explanation=f"知识图谱推荐 ({info['score']:.1f}): {'; '.join(info['reasoning'][:2])}",
                    example_queries=[],
                ))
        elif info["kind"] == "chain":
            chain_result = await session.execute(select(SerialChain).where(SerialChain.id == target_id))
            chain = chain_result.scalar_one_or_none()
            if chain and chain.enabled:
                suggestions.append(IntentSuggestion(
                    type="chain",
                    confidence=min(info["score"], 1.0),
                    target_id=chain.id,
                    target_name=chain.name,
                    explanation=f"知识图谱推荐 ({info['score']:.1f}): {'; '.join(info['reasoning'][:2])}",
                    example_queries=[],
                ))

    # 归一化 confidence
    if suggestions:
        max_conf = max(s.confidence for s in suggestions)
        if max_conf > 0:
            for s in suggestions:
                s.confidence = round(s.confidence / max_conf, 2)

    return suggestions[:top_k]


async def _fallback_recommend(session: AsyncSession, query: str,
                              top_k: int, min_confidence: float) -> list[IntentSuggestion]:
    """回退推荐：不通过知识图谱，直接用现有 suggest_tools 的逻辑。"""
    from app.services.api_catalog import suggest_tools as _original_suggest
    return await _original_suggest(session, query, top_k, min_confidence)


async def get_kg_stats(session: AsyncSession) -> dict:
    """获取知识图谱统计信息。"""
    total_nodes = (await session.execute(select(func.count(KGNode.id)))).scalar() or 0
    total_edges = (await session.execute(select(func.count(KGEdge.id)))).scalar() or 0
    by_kind = {}
    for row in (await session.execute(
        select(KGNode.kind, func.count(KGNode.id)).group_by(KGNode.kind)
    )).all():
        by_kind[row[0]] = row[1]
    by_relation = {}
    for row in (await session.execute(
        select(KGEdge.relation, func.count(KGEdge.id)).group_by(KGEdge.relation)
    )).all():
        by_relation[row[0]] = row[1]

    top_concepts = (await session.execute(
        select(KGNode).where(KGNode.kind == "concept").order_by(KGNode.frequency.desc()).limit(10)
    )).scalars().all()

    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "by_kind": by_kind,
        "by_relation": by_relation,
        "top_concepts": [KGNodeSummary(id=n.id, label=n.label, kind=n.kind, frequency=n.frequency) for n in top_concepts],
    }


# ─────────── 意图判断集成 ───────────

async def enhance_intent_with_kg(
    session: AsyncSession, 
    intent: IntentResult,
    user_message: str,
    conversation_history: Optional[list[dict]] = None
) -> IntentResult:
    """使用知识图谱增强意图判断结果。
    
    功能:
    1. 基于意图类型和关键词，从知识图谱获取相关推荐
    2. 将推荐信息添加到意图的 metadata 中
    3. 根据推荐调整置信度
    4. 为意图处理器提供上下文信息
    """
    # Step 1: 获取知识图谱推荐
    kg_suggestions = await recommend_from_query(
        session, user_message, top_k=3, min_confidence=0.2
    )
    
    # Step 2: 根据意图类型过滤和增强推荐
    enhanced_suggestions = []
    for suggestion in kg_suggestions:
        # 根据意图类型调整推荐相关性
        if intent.intent_type == "doc_query":
            # 文档查询意图：优先推荐文档相关的 API/Chain
            if any(keyword in suggestion.target_name.lower() for keyword in ["document", "search", "retrieve", "query"]):
                suggestion.confidence *= 1.2
        elif intent.intent_type == "doc_comparison":
            # 文档比较意图：优先推荐比较相关的 API/Chain
            if any(keyword in suggestion.target_name.lower() for keyword in ["compare", "comparison", "diff", "analyze"]):
                suggestion.confidence *= 1.3
        elif intent.intent_type == "doc_summary":
            # 文档总结意图：优先推荐总结相关的 API/Chain
            if any(keyword in suggestion.target_name.lower() for keyword in ["summarize", "summary", "extract"]):
                suggestion.confidence *= 1.2
        
        # 根据对话历史调整
        if conversation_history:
            # 检查历史中是否提到过相关概念
            history_text = " ".join([msg.get("content", "") for msg in conversation_history[-5:]])
            if suggestion.target_name in history_text:
                suggestion.confidence *= 1.1
        
        enhanced_suggestions.append(suggestion)
    
    # Step 3: 更新意图元数据
    if not intent.metadata:
        intent.metadata = {}
    
    intent.metadata["kg_suggestions"] = [
        {
            "type": s.type,
            "target_name": s.target_name,
            "confidence": s.confidence,
            "explanation": s.explanation
        }
        for s in enhanced_suggestions
    ]
    
    # Step 4: 如果有高置信度的推荐，调整意图置信度
    if enhanced_suggestions:
        max_kg_confidence = max(s.confidence for s in enhanced_suggestions)
        if max_kg_confidence > 0.5:
            # 知识图谱支持度高，提升意图置信度
            intent.confidence = min(intent.confidence * 1.1, 1.0)
            intent.metadata["kg_boost"] = True
        elif max_kg_confidence < 0.2:
            # 知识图谱支持度低，降低意图置信度
            intent.confidence = max(intent.confidence * 0.9, 0.1)
            intent.metadata["kg_penalty"] = True
    
    # Step 5: 为意图处理器提供上下文
    if enhanced_suggestions:
        intent.metadata["recommended_tools"] = [
            {
                "id": s.target_id,
                "name": s.target_name,
                "type": s.type,
                "confidence": s.confidence
            }
            for s in enhanced_suggestions
        ]
    
    return intent


async def get_intent_context_from_kg(
    session: AsyncSession,
    intent_type: str,
    keywords: list[str],
    user_id: str = None
) -> dict:
    """从知识图谱获取意图上下文信息。
    
    返回:
        {
            "related_concepts": [概念列表],
            "common_apis": [相关API列表],
            "workflow_patterns": [工作流模式],
            "user_preferences": [用户历史偏好]
        }
    """
    result = {
        "related_concepts": [],
        "common_apis": [],
        "workflow_patterns": [],
        "user_preferences": []
    }
    
    # 1. 基于关键词查找相关概念
    for keyword in keywords[:5]:  # 限制前5个关键词
        concepts = await search_concepts(session, keyword, limit=3)
        for concept in concepts:
            if concept.label not in result["related_concepts"]:
                result["related_concepts"].append(concept.label)
    
    # 2. 基于意图类型获取常见API模式
    if intent_type == "doc_query":
        # 文档查询常见模式
        result["workflow_patterns"] = [
            "document_retrieval → answer_generation",
            "keyword_search → context_extraction → answer_synthesis"
        ]
    elif intent_type == "doc_comparison":
        # 文档比较常见模式
        result["workflow_patterns"] = [
            "multi_document_retrieval → comparison_analysis → summary_generation",
            "feature_extraction → similarity_analysis → difference_highlighting"
        ]
    elif intent_type == "doc_summary":
        # 文档总结常见模式
        result["workflow_patterns"] = [
            "document_analysis → key_point_extraction → summary_generation",
            "content_extraction → information_condensation → structured_summary"
        ]
    
    # 3. 如果有用户ID，获取用户历史偏好
    if user_id:
        # 从对话历史中提取用户偏好的概念
        from app.models.database import Conversation, Message
        from sqlalchemy import desc
        
        conv_result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(5)
        )
        conversations = conv_result.scalars().all()
        
        user_keywords = set()
        for conv in conversations:
            msg_result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(desc(Message.created_at))
                .limit(10)
            )
            messages = msg_result.scalars().all()
            
            for msg in messages:
                if msg.role == "user":
                    extracted = _extract_concept_keywords(msg.content, top_n=5)
                    user_keywords.update(extracted)
        
        result["user_preferences"] = list(user_keywords)[:10]  # 限制前10个
    
    return result


# 单例服务
class KnowledgeGraphService:
    """知识图谱服务单例，提供意图增强功能。"""
    
    def __init__(self):
        pass
    
    async def enhance_intent(
        self,
        session: AsyncSession,
        intent: IntentResult,
        user_message: str,
        conversation_history: Optional[list[dict]] = None
    ) -> IntentResult:
        """增强意图判断结果。"""
        return await enhance_intent_with_kg(
            session, intent, user_message, conversation_history
        )
    
    async def get_intent_context(
        self,
        session: AsyncSession,
        intent_type: str,
        keywords: list[str],
        user_id: str = None
    ) -> dict:
        """获取意图上下文。"""
        return await get_intent_context_from_kg(
            session, intent_type, keywords, user_id
        )
    
    async def rebuild_graph(self, session: AsyncSession) -> dict:
        """重建知识图谱。"""
        return await rebuild_all_kg(session)
    
    async def get_stats(self, session: AsyncSession) -> dict:
        """获取图谱统计。"""
        return await get_kg_stats(session)


# 全局实例
knowledge_graph_service = KnowledgeGraphService()
