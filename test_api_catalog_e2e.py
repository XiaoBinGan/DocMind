import asyncio, httpx, json

async def test():
    base = 'http://127.0.0.1:8000'
    async with httpx.AsyncClient(base_url=base, timeout=10) as c:
        print('Phase 1: API CRUD')
        r = await c.post('/api-catalog/', json={
            'name': 'Google Search',
            'base_url': 'https://www.googleapis.com',
            'method': 'GET',
            'path': '/customsearch/v1',
            'description': 'Google Custom Search API',
            'headers': json.dumps({'X-Test': 'header'}),
            'body_schema': json.dumps({'q': 'string'}),
            'auth_type': 'bearer',
            'timeout_ms': 30000
        })
        api = r.json()
        print(f'OK Create API: {api["name"]} id={api["id"][:8]}...')

        r2 = await c.get(f'/api-catalog/{api["id"]}')
        assert r2.json()['name'] == 'Google Search'
        print('OK Get by ID')

        r3 = await c.get('/api-catalog/')
        assert len(r3.json()) == 1
        print('OK List APIs')

        r4 = await c.get('/api-catalog/search', params={'keyword': 'Google'})
        assert len(r4.json()) == 1
        print('OK Search APIs')

        r5 = await c.patch(f'/api-catalog/{api["id"]}/toggle', params={'enabled': 0})
        assert r5.json()['enabled'] == 0
        print('OK Toggle API (disabled)')

        r6 = await c.put(f'/api-catalog/{api["id"]}', json={
            'name': 'Google Search V2',
            'base_url': 'https://www.googleapis.com',
            'method': 'GET',
            'path': '/customsearch/v2',
            'description': 'Updated',
            'headers': {},
            'body_schema': {},
            'auth_type': 'bearer',
            'timeout_ms': 30000
        })
        assert r6.json()['name'] == 'Google Search V2'
        print('OK Update API')

        await c.patch(f'/api-catalog/{api["id"]}/toggle', params={'enabled': 1})

        print()
        print('Phase 2: Chain CRUD')
        r7 = await c.post('/api-catalog/chains', json={
            'name': 'Test Workflow',
            'description': 'API1 chain',
            'members': [
                {'order': 1, 'api_id': api['id'], 'input_mapping': {'q': '{{query}}'}},
            ]
        })
        chain = r7.json()
        print(f'OK Create Chain: {chain["name"]} id={chain["id"][:8]}...')

        r8 = await c.get(f'/api-catalog/chains/{chain["id"]}')
        assert r8.json()['name'] == 'Test Workflow'
        assert r8.json()['steps_count'] == 1
        print('OK Get Chain with members')

        r9 = await c.get('/api-catalog/chains')
        assert len(r9.json()) == 1
        print('OK List Chains')

        r10 = await c.post(f'/api-catalog/chains/{chain["id"]}/execute', json={'input_data': {'query': 'test'}})
        print(f'OK Execute Chain: status={r10.json().get("status")}')

        await c.delete(f'/api-catalog/chains/{chain["id"]}')
        await c.delete(f'/api-catalog/{api["id"]}')
        r11 = await c.get('/api-catalog/')
        r12 = await c.get('/api-catalog/chains')
        assert len(r11.json()) == 0 and len(r12.json()) == 0
        print()
        print('ALL TESTS PASSED')

asyncio.run(test())
