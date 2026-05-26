"""API Catalog routes - mounted at /api-catalog."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db

from app.services.api_catalog import (
    create_api, get_api, list_apis, update_api, delete_api, toggle_api, search_apis,
    create_chain, get_chain, list_chains, update_chain, delete_chain, execute_chain,
    suggest_tools, execute_api_direct,
)
from app.services.knowledge_graph import (
    rebuild_all_kg, search_concepts, get_neighbors, recommend_from_query, get_kg_stats,
)
from app.services.serial_chain import (
    create_chain as create_chain_svc,
    get_chain as get_chain_svc,
    list_chains as list_chains_svc,
    update_chain as update_chain_svc,
    delete_chain as delete_chain_svc,
    execute_chain as execute_chain_svc,
)
from app.models.schemas import (
    ApiDefinitionCreate, ApiDefinitionUpdate, ApiDefinitionResponse,
    SerialChainCreate, SerialChainResponse,
    ChainExecuteRequest, ChainExecuteResponse,
)

router = APIRouter(prefix="/api-catalog", tags=["API Catalog"])


# ---- Session dependency ----


# ---- Static paths MUST come before wildcard paths ----

@router.post("/", response_model=ApiDefinitionResponse)
async def create_api_endpoint(data: ApiDefinitionCreate, session: AsyncSession = Depends(get_db)):
    return await create_api(session, data)


@router.get("/", response_model=list[ApiDefinitionResponse])
async def list_apis_endpoint(session: AsyncSession = Depends(get_db)):
    return await list_apis(session)


@router.get("/search")
async def search_apis_endpoint(keyword: str = Query(..., min_length=1), session: AsyncSession = Depends(get_db)):
    return await search_apis(session, keyword)


@router.get("/apis")
async def list_apis_endpoint_alias(session: AsyncSession = Depends(get_db)):
    return await list_apis(session)


@router.post("/chains", response_model=SerialChainResponse)
async def create_chain_endpoint(data: SerialChainCreate, session: AsyncSession = Depends(get_db)):
    return await create_chain_svc(session, data)


@router.get("/chains", response_model=list[SerialChainResponse])
async def list_chains_endpoint(session: AsyncSession = Depends(get_db)):
    return await list_chains_svc(session)


@router.get("/chains/{chain_id}", response_model=SerialChainResponse)
async def get_chain_endpoint(chain_id: str, session: AsyncSession = Depends(get_db)):
    result = await get_chain_svc(session, chain_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chain not found")
    return result


@router.put("/chains/{chain_id}", response_model=SerialChainResponse)
async def update_chain_endpoint(chain_id: str, data: SerialChainCreate, session: AsyncSession = Depends(get_db)):
    result = await update_chain_svc(session, chain_id, data)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chain not found")
    return result


@router.delete("/chains/{chain_id}")
async def delete_chain_endpoint(chain_id: str, session: AsyncSession = Depends(get_db)):
    deleted = await delete_chain_svc(session, chain_id)
    return {"deleted": deleted}


@router.post("/chains/{chain_id}/execute", response_model=ChainExecuteResponse)
async def execute_chain_endpoint(chain_id: str, data: ChainExecuteRequest = ChainExecuteRequest(), session: AsyncSession = Depends(get_db)):
    return await execute_chain_svc(session, chain_id, data.input_data)


@router.get("/suggest", summary="智能推荐 API 和工作流")
async def suggest_endpoint(query: str = Query(..., min_length=1), session: AsyncSession = Depends(get_db)):
    """根据用户消息智能推荐 API 和 Chain。
    
    返回 top-3 匹配的 API 或 Chain，包含置信度和推荐原因。
    """
    suggestions = await suggest_tools(session, query)
    # 将 Pydantic model 转为 dict 避免序列化错误
    result = []
    for s in suggestions:
        result.append({
            "type": s.type,
            "confidence": s.confidence,
            "target_id": s.target_id,
            "target_name": s.target_name,
            "explanation": s.explanation,
            "example_queries": s.example_queries,
        })
    return {"suggestions": result}


# ---- Wildcard paths (MUST be last) ----

@router.get("/{api_id}", response_model=ApiDefinitionResponse)
async def get_api_endpoint(api_id: str, session: AsyncSession = Depends(get_db)):
    result = await get_api(session, api_id)
    if result is None:
        raise HTTPException(status_code=404, detail="API not found")
    return result


@router.put("/{api_id}", response_model=ApiDefinitionResponse)
async def update_api_endpoint(api_id: str, data: ApiDefinitionUpdate, session: AsyncSession = Depends(get_db)):
    return await update_api(session, api_id, data)


@router.delete("/{api_id}")
async def delete_api_endpoint(api_id: str, session: AsyncSession = Depends(get_db)):
    deleted = await delete_api(session, api_id)
    return {"deleted": deleted}


@router.patch("/{api_id}/toggle")
async def toggle_api_endpoint(api_id: str, enabled: bool = Query(...), session: AsyncSession = Depends(get_db)):
    return await toggle_api(session, api_id, enabled)


# ---- API Direct Execution ----

@router.post("/apis/{api_id}/execute", summary="直接执行 API")
async def execute_api_endpoint(
    api_id: str,
    data: ChainExecuteRequest = ChainExecuteRequest(),
    session: AsyncSession = Depends(get_db),
):
    """直接执行一个已注册的 API（无需通过 Chain）。"""
    result = await execute_api_direct(session, api_id, data.input_data)
    return result


# ──────────────── ���识图谱 ────────────────

@router.post("/kg/rebuild", summary="重建知识图谱")
async def rebuild_kg_endpoint(session: AsyncSession = Depends(get_db)):
    """重建知识图谱（清除旧数据并重新扫描）。"""
    result = await rebuild_all_kg(session)
    return {"status": "ok", "details": result}


@router.get("/kg/stats", summary="知识图谱统计")
async def kg_stats_endpoint(session: AsyncSession = Depends(get_db)):
    """获取知识图谱统计信息。"""
    stats = await get_kg_stats(session)
    return stats


@router.get("/kg/search", summary="搜索概念节点")
async def kg_search_endpoint(
    keyword: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
):
    """搜索知识图谱中的概念节点。"""
    nodes = await search_concepts(session, keyword, limit)
    return {"nodes": [n.to_dict() for n in nodes]}


@router.get("/kg/neighbors/{node_id}", summary="获取节点邻居")
async def kg_neighbors_endpoint(
    node_id: str,
    max_depth: int = Query(2, ge=1, le=3),
    session: AsyncSession = Depends(get_db),
):
    """获取知识图谱中节点的邻居（多跳）。"""
    data = await get_neighbors(session, node_id, max_depth)
    return data


@router.get("/kg/recommend", summary="知识图谱推荐")
async def kg_recommend_endpoint(
    query: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=10),
    min_confidence: float = Query(0.3, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_db),
):
    """基于知识图谱为用户查询推荐 API/工作流。"""
    suggestions = await recommend_from_query(session, query, top_k, min_confidence)
    return {"suggestions": [s.dict() for s in suggestions]}


import json as _json


@router.get("/kg/nodes", summary="获取所有KG节点")
async def kg_list_nodes(
    kind: str = Query(None, description="节点类型过滤(concept/api/chain/document)"),
    session: AsyncSession = Depends(get_db),
):
    """获取知识图谱所有节点。"""
    from app.models.database import KGNode
    from sqlalchemy import select

    q = select(KGNode)
    if kind:
        q = q.where(KGNode.kind == kind)
    result = await session.execute(q)
    nodes = result.scalars().all()
    return {"nodes": [
        {
            "id": n.id,
            "label": n.label,
            "kind": n.kind,
            "source_id": n.source_id,
            "frequency": n.frequency,
            "payload": _json.loads(n.payload) if n.payload else {},
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in nodes
    ]}


@router.get("/kg/edges", summary="获取所有KG边")
async def kg_list_edges(
    session: AsyncSession = Depends(get_db),
):
    """获取知识图谱所有边。"""
    from app.models.database import KGEdge
    from sqlalchemy import select

    q = select(KGEdge)
    result = await session.execute(q)
    edges = result.scalars().all()
    return {"edges": [
        {
            "id": e.id,
            "source_id": e.source_id,
            "target_id": e.target_id,
            "relation": e.relation,
            "weight": e.weight,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in edges
    ]}
