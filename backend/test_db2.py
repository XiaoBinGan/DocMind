import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())

from app.main import async_session_maker
from app.services.api_catalog import list_apis, _api_to_response
from app.models.database import ApiDefinition
from sqlalchemy import text

async def test():
    async with async_session_maker() as session:
        # Check tables
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        print("Tables:", [r[0] for r in result])
        
        # Check columns
        result = await session.execute(text("PRAGMA table_info(api_definitions)"))
        print("api_definitions columns:", [(r[1], r[2]) for r in result])
        
        # Test query
        from sqlalchemy import select
        result = await session.execute(select(ApiDefinition))
        rows = result.scalars().all()
        print(f"API rows: {len(rows)}")
        
        if rows:
            api = rows[0]
            try:
                resp = _api_to_response(api)
                print(f"Response: {resp}")
            except Exception as e:
                print(f"_api_to_response error: {type(e).__name__}: {e}")

asyncio.run(test())
