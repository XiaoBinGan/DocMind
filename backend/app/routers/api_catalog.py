"""API Catalog routes - mounted at /api-catalog."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.api_catalog import (
    create_api, get_api, list_apis, update_api, delete_api, toggle_api, search_apis,
    create_chain, get_chain, list_chains, update_chain, delete_chain, execute_chain,
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

async def get_db():
    """Yield an async database session."""
    from app.main import async_session_maker
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---- API Definition endpoints ----

@router.post("/", response_model=ApiDefinitionResponse)
async def create_api_endpoint(data: ApiDefinitionCreate, session: AsyncSession = Depends(get_db)):
    return await create_api(session, data)


@router.get("/", response_model=list[ApiDefinitionResponse])
async def list_apis_endpoint(session: AsyncSession = Depends(get_db)):
    return await list_apis(session)


@router.get("/search")
async def search_apis_endpoint(keyword: str = Query(..., min_length=1), session: AsyncSession = Depends(get_db)):
    return await search_apis(session, keyword)


# ---- Serial Chain endpoints (MUST be before /{api_id} to avoid path param collision) ----

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


# ---- Wildcard endpoints (MUST be last) ----

@router.get("/{api_id}", response_model=ApiDefinitionResponse)
async def get_api_endpoint(api_id: str, session: AsyncSession = Depends(get_db)):
    return await get_api(session, api_id)


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
