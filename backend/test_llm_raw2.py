import asyncio
import sys
sys.path.insert(0, '.')

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
    
    # Write to file with UTF-8
    with open('llm_raw_output2.txt', 'w', encoding='utf-8') as f:
        f.write(f'Provider: {provider}\n')
        f.write(f'Base URL: {base_url}\n')
        f.write(f'Model: {model}\n\n')
        
        system = 'You are DocMind.'
        user = '请用中文回答，包含一个Python代码块和一个表格。'
        f.write('=== Raw stream chunks ===\n')
        chunks = []
        async for chunk in llm_service.generate(system, user, stream=True):
            chunks.append(chunk)
            f.write(f'CHUNK [{len(chunk)} chars]: {repr(chunk)}\n')
        
        f.write('\n=== Full response ===\n')
        full = ''.join(chunks)
        f.write(full)
        f.write(f'\n\nTotal chunks: {len(chunks)}, Total chars: {len(full)}\n')
    
    await engine.dispose()
    print('Done! Check llm_raw_output2.txt')

if __name__ == '__main__':
    asyncio.run(test())
