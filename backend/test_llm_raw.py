import asyncio
import sys
import os
sys.path.insert(0, '.')
os.environ['PYTHONIOENCODING'] = 'utf-8'

async def test():
    from app.services.llm import llm_service
    from app.services.settings_service import settings_service
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    settings_service.init(sm)
    
    provider = await settings_service.llm_provider()
    base_url = await settings_service.llm_base_url()
    model = await settings_service.llm_model()
    print(f'Provider: {provider}')
    print(f'Base URL: {base_url}')
    print(f'Model: {model}')
    
    system = 'You are DocMind.'
    user = 'Say hello in markdown with a code block and a table.'
    print()
    print('=== Raw stream chunks ===')
    chunks = []
    async for chunk in llm_service.generate(system, user, stream=True):
        chunks.append(chunk)
        print(f'CHUNK [{len(chunk)} chars]: {repr(chunk)}')
    
    print()
    print('=== Full response ===')
    full = ''.join(chunks)
    print(full)
    print()
    print(f'Total chunks: {len(chunks)}, Total chars: {len(full)}')
    
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(test())
