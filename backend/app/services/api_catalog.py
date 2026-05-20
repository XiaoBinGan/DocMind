"""API Catalog service - CRUD + search for ApiDefinition and SerialChain."""

import json
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import ApiDefinition, SerialChain, SerialChainMember, Base
from app.models.schemas import (
    ApiDefinitionCreate, ApiDefinitionUpdate, ApiDefinitionResponse,
    SerialChainCreate, SerialChainResponse, ChainMemberResponse,
    ChainExecuteRequest, ChainExecuteResponse, IntentSuggestion,
    ApiUsageLogCreate,
)
from app.models.database import ApiUsageLog


async def create_api(session: AsyncSession, data: ApiDefinitionCreate) -> ApiDefinitionResponse:
    """Create a new API definition."""
    api = ApiDefinition(
        name=data.name,
        description=data.description,
        base_url=data.base_url,
        method=data.method,
        path=data.path,
        headers=json.dumps(data.headers) if data.headers else "{}",
        body_schema=json.dumps(data.body_schema) if data.body_schema else "{}",
        auth_type=data.auth_type,
        auth_header=data.auth_header,
        timeout_ms=data.timeout_ms,
    )
    session.add(api)
    await session.flush()
    await session.refresh(api)
    return _api_to_response(api)


async def get_api(session: AsyncSession, api_id: str) -> Optional[ApiDefinitionResponse]:
    """Get a single API definition by ID."""
    result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == api_id))
    api = result.scalar_one_or_none()
    return _api_to_response(api) if api else None


async def list_apis(session: AsyncSession, enabled_only: bool = True) -> list[ApiDefinitionResponse]:
    """List all API definitions."""
    query = select(ApiDefinition)
    if enabled_only:
        query = query.where(ApiDefinition.enabled == 1)
    query = query.order_by(ApiDefinition.updated_at.desc())
    result = await session.execute(query)
    apis = result.scalars().all()
    return [_api_to_response(a) for a in apis]


async def update_api(session: AsyncSession, api_id: str, data: ApiDefinitionUpdate) -> Optional[ApiDefinitionResponse]:
    """Update an API definition."""
    result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == api_id))
    api = result.scalar_one_or_none()
    if not api:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "headers":
            setattr(api, field, json.dumps(value) if value else "{}")
        elif field == "body_schema":
            setattr(api, field, json.dumps(value) if value else "{}")
        elif field == "example_queries":
            setattr(api, field, json.dumps(value) if value else "[]")
        elif field == "expected_response":
            setattr(api, field, json.dumps(value) if value else "{}")
        elif field == "enabled":
            setattr(api, field, 1 if value else 0)
        else:
            setattr(api, field, value)
    await session.flush()
    await session.refresh(api)
    return _api_to_response(api)


async def delete_api(session: AsyncSession, api_id: str) -> bool:
    """Delete an API definition."""
    result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == api_id))
    api = result.scalar_one_or_none()
    if not api:
        return False
    await session.delete(api)
    await session.flush()
    return True


async def toggle_api(session: AsyncSession, api_id: str, enabled: bool) -> Optional[ApiDefinitionResponse]:
    """Toggle API enabled/disabled."""
    result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == api_id))
    api = result.scalar_one_or_none()
    if not api:
        return None
    api.enabled = 1 if enabled else 0
    await session.flush()
    await session.refresh(api)
    return _api_to_response(api)


async def search_apis(session: AsyncSession, keyword: str) -> list[ApiDefinitionResponse]:
    """Search APIs by name or description."""
    search_pattern = f"%{keyword}%"
    result = await session.execute(
        select(ApiDefinition).where(
            (ApiDefinition.name.ilike(search_pattern)) |
            (ApiDefinition.description.ilike(search_pattern))
        ).order_by(ApiDefinition.name)
    )
    apis = result.scalars().all()
    return [_api_to_response(a) for a in apis]


async def create_chain(session: AsyncSession, data: SerialChainCreate) -> SerialChainResponse:
    """Create a new serial chain."""
    chain = SerialChain(
        name=data.name,
        description=data.description,
        steps_count=len(data.members),
    )
    session.add(chain)
    await session.flush()

    for member_data in data.members:
        member = SerialChainMember(
            chain_id=chain.id,
            order=member_data.order,
            api_id=member_data.api_id,
            input_mapping=json.dumps(member_data.input_mapping) if member_data.input_mapping else "{}",
            output_mapping=json.dumps(member_data.output_mapping) if member_data.output_mapping else "{}",
        )
        session.add(member)

    await session.flush()

    m_result = await session.execute(
        select(SerialChainMember).where(SerialChainMember.chain_id == chain.id).order_by(SerialChainMember.order)
    )
    members = m_result.scalars().all()

    return _chain_to_response(chain, members)


async def get_chain(session: AsyncSession, chain_id: str) -> Optional[SerialChainResponse]:
    """Get a chain with its members."""
    result = await session.execute(select(SerialChain).where(SerialChain.id == chain_id))
    chain = result.scalar_one_or_none()
    if not chain:
        return None
    m_result = await session.execute(
        select(SerialChainMember).where(SerialChainMember.chain_id == chain_id).order_by(SerialChainMember.order)
    )
    members = m_result.scalars().all()
    return _chain_to_response(chain, members)


async def list_chains(session: AsyncSession) -> list[SerialChainResponse]:
    """List all chains."""
    result = await session.execute(select(SerialChain).order_by(SerialChain.updated_at.desc()))
    chains = result.scalars().all()
    responses = []
    for c in chains:
        m_result = await session.execute(
            select(SerialChainMember).where(SerialChainMember.chain_id == c.id).order_by(SerialChainMember.order)
        )
        members = m_result.scalars().all()
        responses.append(_chain_to_response(c, members))
    return responses


async def update_chain(session: AsyncSession, chain_id: str, data: SerialChainCreate) -> Optional[SerialChainResponse]:
    """Update a chain (replaces all members)."""
    result = await session.execute(select(SerialChain).where(SerialChain.id == chain_id))
    chain = result.scalar_one_or_none()
    if not chain:
        return None

    chain.name = data.name
    chain.description = data.description
    chain.steps_count = len(data.members)

    # Delete old members
    old_members = await session.execute(
        select(SerialChainMember).where(SerialChainMember.chain_id == chain_id)
    )
    for m in old_members.scalars().all():
        await session.delete(m)

    # Add new members
    for member_data in data.members:
        member = SerialChainMember(
            chain_id=chain_id,
            order=member_data.order,
            api_id=member_data.api_id,
            input_mapping=json.dumps(member_data.input_mapping) if member_data.input_mapping else "{}",
            output_mapping=json.dumps(member_data.output_mapping) if member_data.output_mapping else "{}",
        )
        session.add(member)

    await session.flush()
    await session.refresh(chain)
    m_result = await session.execute(
        select(SerialChainMember).where(SerialChainMember.chain_id == chain_id).order_by(SerialChainMember.order)
    )
    members = m_result.scalars().all()
    return _chain_to_response(chain, members)


async def delete_chain(session: AsyncSession, chain_id: str) -> bool:
    """Delete a chain."""
    result = await session.execute(select(SerialChain).where(SerialChain.id == chain_id))
    chain = result.scalar_one_or_none()
    if not chain:
        return False
    await session.delete(chain)
    await session.flush()
    return True


async def execute_chain(session: AsyncSession, chain_id: str, input_data: dict) -> ChainExecuteResponse:
    """Execute a serial chain - returns plan only (actual HTTP execution is separate)."""
    result = await session.execute(
        select(SerialChain).where(SerialChain.id == chain_id)
    )
    chain = result.scalar_one_or_none()
    if not chain:
        return ChainExecuteResponse(
            chain_id=chain_id, chain_name="", status="failed", steps=[],
            total_duration_ms=0, error="Chain not found"
        )

    members_result = await session.execute(
        select(SerialChainMember).where(SerialChainMember.chain_id == chain_id).order_by(SerialChainMember.order)
    )
    members = members_result.scalars().all()

    steps = []
    context = dict(input_data)

    for m in members:
        api_result = await session.execute(select(ApiDefinition).where(ApiDefinition.id == m.api_id))
        api = api_result.scalar_one_or_none()
        if not api:
            steps.append({"order": m.order, "api_name": "", "status": "error", "error": "API not found"})
            continue

        try:
            input_mapping = json.loads(m.input_mapping) if m.input_mapping else {}
            resolved_input = {}
            for k, v in input_mapping.items():
                if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
                    var_name = v[2:-2].strip()
                    resolved_input[k] = context.get(var_name, None)
                else:
                    resolved_input[k] = v

            # Execute the actual HTTP call (placeholder - real execution needs httpx)
            steps.append({
                "order": m.order,
                "api_name": api.name,
                "status": "success",
                "input": resolved_input,
            })
            # Simple pass-through context
            context[f"step_{m.order}_output"] = {"status": "ok"}

        except Exception as e:
            steps.append({
                "order": m.order,
                "api_name": api.name,
                "status": "error",
                "error": str(e),
            })

    return ChainExecuteResponse(
        chain_id=chain_id,
        chain_name=chain.name,
        status="success" if all(s["status"] == "success" for s in steps) else "partial",
        steps=steps,
        total_duration_ms=0,
    )


# ── 工具推荐服务 ──

def _jaccard_similarity(a: str, b: str) -> float:
    """计算两个文本的 Jaccard 相似度（基于分词后的集合）。
    
    用简单的空格/标点分词，对中文支持字符级 bigram + 空格分词混合。
    """
    import re
    # 简单分词：中文字符单独成词，英文/数字按空格和标点分割
    def tokenize(text: str) -> set[str]:
        if not text:
            return set()
        # 先提取中文字符序列
        cjk_chars = set(re.findall(r'[\u4e00-\u9fff]', text))
        # 再提取英文/数字单词
        words = set(re.findall(r'[a-zA-Z0-9]+', text))
        return cjk_chars | words

    set_a = tokenize(a)
    set_b = tokenize(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


async def suggest_tools(session: AsyncSession, query: str, top_k: int = 3, min_confidence: float = 0.3) -> list[IntentSuggestion]:
    """根据用户输入智能推荐 API 和 Chain。
    
    评分逻辑（加权）：
    1. name 包含 query → +0.6
    2. name 包含 query 子串 → +0.4
    3. description 包含 query → +0.3
    4. example_queries 精确匹配 → +0.8
    5. example_queries 子串匹配 → +0.5
    6. Chain: name 包含 query → +0.6
    
    confidence 是相对排名：最高分=1.0，其余按比例缩放
    """
    from app.models.database import ApiDefinition, SerialChain, SerialChainMember

    # 获取所有已启用的 API
    api_result = await session.execute(
        select(ApiDefinition).where(ApiDefinition.enabled == 1)
    )
    apis = api_result.scalars().all()

    # 获取所有已启用的 Chain
    chain_result = await session.execute(
        select(SerialChain).where(SerialChain.enabled == 1)
    )
    chains = chain_result.scalars().all()

    query_lower = query.lower().strip()
    suggestions: list[IntentSuggestion] = []

    # ---- 遍历 API 计算评分 ----
    for api in apis:
        score = 0.0
        match_fields: list[str] = []

        name_lower = api.name.lower() if api.name else ""
        desc_lower = (api.description or "").lower()

        # 1. name 完全包含 query → +0.6
        if query_lower and query_lower in name_lower:
            score += 0.6
            match_fields.append(f"名称包含「{query}」")
        # 2. name 包含 query 的子串（>=3字符）→ +0.4
        elif query_lower and len(query_lower) >= 3:
            for i in range(len(query_lower) - 2):
                for j in range(i + 3, len(query_lower) + 1):
                    if query_lower[i:j] in name_lower:
                        score += 0.35
                        match_fields.append(f"名称匹配「{query[i:j]}」")
                        break
                if score >= 0.35:
                    break

        # 3. description 包含 query → +0.3
        if desc_lower and query_lower and query_lower in desc_lower:
            score += 0.3
            match_fields.append(f"描述匹配「{query}」")

        # 4. example_queries 精确匹配 → +0.8
        example_queries = json.loads(api.example_queries) if api.example_queries else []
        for eq in example_queries:
            eq_lower = eq.strip().lower()
            if eq_lower == query_lower:
                score += 0.8
                match_fields.append(f"触发词「{eq}」")
                break

        # 5. example_queries 子串匹配 → +0.5
        if example_queries and score < 0.3:
            for eq in example_queries:
                eq_lower = eq.strip().lower()
                if query_lower in eq_lower or eq_lower in query_lower:
                    score += 0.5
                    match_fields.append(f"示例匹配「{eq}」")
                    break

        if score < min_confidence:
            continue

        # 构建有用信息
        method_path = f"{api.method} {api.base_url}{api.path}" if api.base_url and api.path else api.method or api.path or "未知"
        explanation = f"{method_path}  —  {match_fields[-1]}"
        if api.description:
            desc_preview = api.description[:80].replace("\n", " ")
            explanation += f"  |  {desc_preview}"

        # Collect example queries that matched
        matched_examples = [eq for eq in (json.loads(api.example_queries) if api.example_queries else []) if query_lower in eq.lower() or eq.lower() in query_lower]

        confidence = score  # 原始分数，后续会做归一化

        suggestions.append(IntentSuggestion(
            type="api",
            confidence=confidence,
            target_id=api.id,
            target_name=api.name,
            explanation=explanation,
            example_queries=matched_examples[:3] if matched_examples else [],
        ))

    # ---- 遍历 Chain 计算评分 ----
    for chain in chains:
        score = 0.0
        match_fields: list[str] = []

        name_lower = chain.name.lower() if chain.name else ""

        # name 包含 query → +0.6
        if query_lower and query_lower in name_lower:
            score += 0.6
            match_fields.append(f"工作流名称包含「{query}」")
        elif query_lower and len(query_lower) >= 3:
            for i in range(len(query_lower) - 2):
                for j in range(i + 3, len(query_lower) + 1):
                    if query_lower[i:j] in name_lower:
                        score += 0.4
                        match_fields.append(f"名称匹配「{query[i:j]}」")
                        break
                if score >= 0.4:
                    break

        # Chain description 包含 query → +0.3
        desc_lower = (chain.description or "").lower()
        if desc_lower and query_lower and query_lower in desc_lower:
            score += 0.3
            match_fields.append(f"描述匹配「{query}」")

        # Chain 成员 API 名称匹配 → +0.2 * 匹配数
        if score > 0:
            chain_desc_parts = [desc for desc in match_fields]
            desc_preview = chain.description[:60].replace("\n", " ") if chain.description else "串行工作流"
            explanation = f"包含 {chain.steps_count} 步  —  {match_fields[-1]}"
            if desc_preview:
                explanation += f"  |  {desc_preview}"
            else:
                explanation += f"  |  {chain.steps_count} 步串行调用"
        elif score < min_confidence:
            continue
        else:
            explanation = f"工作流「{chain.name}」 — {match_fields[-1]}"

        if score < min_confidence:
            continue

        confidence = score

        suggestions.append(IntentSuggestion(
            type="chain",
            confidence=confidence,
            target_id=chain.id,
            target_name=chain.name,
            explanation=explanation,
            example_queries=[],
        ))

    if not suggestions:
        return []

    # 按 score 降序，最高分归一化为 1.0
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    max_score = suggestions[0].confidence

    for s in suggestions:
        if max_score > 0:
            s.confidence = round(s.confidence / max_score, 2)
        else:
            s.confidence = 0.0

    return suggestions[:top_k]


async def log_api_usage(session: AsyncSession, data: ApiUsageLogCreate) -> None:
    """Log an API usage."""
    log = ApiUsageLog(
        chain_id=data.chain_id,
        api_id=data.api_id,
        request_payload=json.dumps(data.request_payload) if data.request_payload else "{}",
        response_payload=json.dumps(data.response_payload) if data.response_payload else "{}",
        status_code=data.status_code,
        duration_ms=data.duration_ms,
        error=data.error,
    )
    session.add(log)
    await session.flush()


def _api_to_response(api: ApiDefinition) -> ApiDefinitionResponse:
    """Convert ORM model to response schema."""
    return ApiDefinitionResponse(
        id=api.id,
        name=api.name,
        description=api.description,
        base_url=api.base_url,
        method=api.method,
        path=api.path,
        headers=json.loads(api.headers) if api.headers else {},
        body_schema=json.loads(api.body_schema) if api.body_schema else {},
        auth_type=api.auth_type,
        auth_header=api.auth_header,
        timeout_ms=api.timeout_ms,
        enabled=api.enabled,
        example_queries=json.loads(api.example_queries) if api.example_queries else [],
        expected_response=json.loads(api.expected_response) if api.expected_response else {},
        created_at=api.created_at,
        updated_at=api.updated_at,
        created_by=api.created_by,
    )


def _chain_to_response(chain: SerialChain, members: list[SerialChainMember] | None = None) -> SerialChainResponse:
    """Convert ORM model to response."""
    members = members or []
    return SerialChainResponse(
        id=chain.id,
        name=chain.name,
        description=chain.description,
        steps_count=chain.steps_count,
        enabled=chain.enabled,
        members=[_member_to_response(m) for m in members],
        created_at=chain.created_at,
        updated_at=chain.updated_at,
        created_by=chain.created_by,
    )


def _member_to_response(member: SerialChainMember) -> ChainMemberResponse:
    """Convert member ORM to response with api name."""
    api_name = ""
    try:
        api = member.api
        if api:
            api_name = api.name
    except Exception:
        api_name = ""
    return ChainMemberResponse(
        id=member.id,
        order=member.order,
        api_id=member.api_id,
        api_name=api_name,
        input_mapping=json.loads(member.input_mapping) if member.input_mapping else {},
        output_mapping=json.loads(member.output_mapping) if member.output_mapping else {},
        created_at=member.created_at,
    )
