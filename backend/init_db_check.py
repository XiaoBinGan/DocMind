import asyncio
from app.main import engine, init_db
from app.models.database import Base

async def check():
    # Check what's in metadata
    print("Tables in metadata:", list(Base.metadata.tables.keys()))
    print()
    # Try to create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("After create_all:")
    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        for row in result:
            print(" -", row[0])

asyncio.run(check())
