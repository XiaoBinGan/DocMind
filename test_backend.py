import asyncio, httpx, json

async def t():
    b = 'http://127.0.0.1:8000'
    async with httpx.AsyncClient(base_url=b, timeout=10) as c:
        # Create API
        r = await c.post('/api-catalog/', json={
            'name': 'T1', 'base_url': 'https://a.com',
            'method': 'GET', 'path': '/v1', 'description': 'd',
            'headers': {}, 'body_schema': {}, 'auth_type': 'none',
            'timeout_ms': 30000
        })
        api = r.json()
        print(f'CREATE {r.status_code} {api["name"]}')
        assert r.status_code == 200

        # Get
        r = await c.get(f'/api-catalog/{api["id"]}')
        print(f'GET {r.status_code}')
        assert r.status_code == 200

        # List
        r = await c.get('/api-catalog/')
        print(f'LIST {r.status_code} count={len(r.json())}')
        assert r.status_code == 200 and len(r.json()) >= 1

        # Search
        r = await c.get('/api-catalog/search', params={'keyword': 'T1'})
        print(f'SEARCH {r.status_code} count={len(r.json())}')
        assert r.status_code == 200

        # Update
        r = await c.put(f'/api-catalog/{api["id"]}', json={
            'name': 'T2', 'base_url': 'https://a.com',
            'method': 'GET', 'path': '/v1', 'description': 'updated',
            'headers': {}, 'body_schema': {}, 'auth_type': 'none',
            'timeout_ms': 30000
        })
        print(f'UPDATE {r.status_code} {r.json()["name"]}')
        assert r.json()["name"] == 'T2'

        # Toggle off
        r = await c.patch(f'/api-catalog/{api["id"]}/toggle', params={'enabled': 0})
        print(f'TOGGLE_OFF {r.status_code} enabled={r.json()["enabled"]}')
        assert r.json()["enabled"] == 0

        # Toggle on
        r = await c.patch(f'/api-catalog/{api["id"]}/toggle', params={'enabled': 1})
        print(f'TOGGLE_ON {r.status_code} enabled={r.json()["enabled"]}')
        assert r.json()["enabled"] == 1

        # Create chain
        r = await c.post('/api-catalog/chains', json={
            'name': 'C1', 'description': 'd',
            'members': [{'order': 1, 'api_id': api['id'], 'input_mapping': {'q': 'test'}}]
        })
        ch = r.json()
        print(f'CHAIN_CREATE {r.status_code} {ch["name"]} steps={ch["steps_count"]}')
        assert r.status_code == 200 and ch["steps_count"] == 1

        # Get chain with members
        r = await c.get(f'/api-catalog/chains/{ch["id"]}')
        print(f'CHAIN_GET {r.status_code} steps={r.json()["steps_count"]} members={len(r.json()["members"])}')
        assert r.json()["steps_count"] == 1

        # List chains
        r = await c.get('/api-catalog/chains')
        print(f'CHAIN_LIST {r.status_code} count={len(r.json())}')
        assert r.status_code == 200

        # Execute chain
        r = await c.post(f'/api-catalog/chains/{ch["id"]}/execute', json={'input_data': {'test': 'x'}})
        print(f'CHAIN_EXEC {r.status_code}')
        assert r.status_code == 200

        # Cleanup
        await c.delete(f'/api-catalog/{api["id"]}')
        await c.delete(f'/api-catalog/chains/{ch["id"]}')
        r = await c.get('/api-catalog/')
        r2 = await c.get('/api-catalog/chains')
        print(f'CLEANUP APIs={len(r.json())} CHAINS={len(r2.json())}')
        assert len(r.json()) == 0 and len(r2.json()) == 0

        print('\nALL BACKEND TESTS PASSED')

asyncio.run(t())
