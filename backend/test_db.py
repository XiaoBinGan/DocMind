import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())

from app.main import async_session_maker
from app.services.api_catalog import list_apis
from app.services.serial_chain import list_chains

async def test():
    # Test list_apis
    async with async_session_maker() as session:
        try:
            apis = await list_apis(session, enabled_only=False)
            print(f"list_apis(enabled_only=False): {len(apis)} results")
        except Exception as e:
            print(f"list_apis ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        print()
        
        # Test list_chains  
        try:
            chains = await list_chains(session)
            print(f"list_chains: {len(chains)} results")
        except Exception as e:
            print(f"list_chains ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        print()
        
        # List all tables
        from sqlalchemy import text
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        print(f"Tables: {[r[0] for r in result]}")
        
        # Check column info
        for table in ['api_definitions', 'serial_chains', 'serial_chain_members']:
            result = await session.execute(text(f"PRAGMA table_info({table})"))
            cols = [(r[1], r[2]) for r in result]
            print(f"  {table} columns: {cols}")

asyncio.run(test())
