import asyncio, httpx, json

async def test_all():
    base = "http://127.0.0.1:8000"
    results = []
    
    # 1. API CRUD
    async with httpx.AsyncClient(base_url=base, timeout=10) as c:
        print("=" * 50)
        print("TEST 1: API CRUD")
        print("=" * 50)
        
        # Create
        r = await c.post("/api-catalog/", json={
            "name": "Test API",
            "base_url": "https://api.example.com",
            "method": "GET",
            "path": "/v1/test",
            "description": "Test description",
            "headers": json.dumps({"X-Custom": "value"}),
            "body_schema": json.dumps({"q": "string"}),
            "auth_type": "bearer",
            "timeout_ms": 30000
        })
        assert r.status_code == 200
        api = r.json()
        print(f"  CREATE: OK ({api['name']})")
        
        # Get
        r = await c.get(f"/api-catalog/{api['id']}")
        assert r.status_code == 200 and r.json()["name"] == "Test API"
        print("  GET: OK")
        
        # List
        r = await c.get("/api-catalog/")
        assert r.status_code == 200 and len(r.json()) == 1
        print("  LIST: OK")
        
        # Search
        r = await c.get("/api-catalog/search", params={"keyword": "Test"})
        assert r.status_code == 200 and len(r.json()) == 1
        print("  SEARCH: OK")
        
        # Update
        r = await c.put(f"/api-catalog/{api['id']}", json={
            "name": "Updated API",
            "base_url": "https://api.example.com",
            "method": "GET",
            "path": "/v1/test",
            "description": "Updated",
            "headers": {},
            "body_schema": {},
            "auth_type": "bearer",
            "timeout_ms": 30000
        })
        assert r.status_code == 200 and r.json()["name"] == "Updated API"
        print("  UPDATE: OK")
        
        # Toggle
        r = await c.patch(f"/api-catalog/{api['id']}/toggle", params={"enabled": 0})
        assert r.status_code == 200 and r.json()["enabled"] == 0
        print("  TOGGLE OFF: OK")
        
        r = await c.patch(f"/api-catalog/{api['id']}/toggle", params={"enabled": 1})
        assert r.status_code == 200 and r.json()["enabled"] == 1
        print("  TOGGLE ON: OK")
        
        # Delete
        r = await c.delete(f"/api-catalog/{api['id']}")
        assert r.status_code == 200 and r.json()["deleted"] == True
        r = await c.get("/api-catalog/")
        assert len(r.json()) == 0
        print("  DELETE: OK")
        
        print()
        print("=" * 50)
        print("TEST 2: Chain CRUD")
        print("=" * 50)
        
        # Create API for chain members
        r = await c.post("/api-catalog/", json={
            "name": "API1",
            "base_url": "https://api.example.com",
            "method": "GET",
            "path": "/v1",
            "description": "API1",
            "headers": {},
            "body_schema": {},
            "auth_type": "none",
            "timeout_ms": 30000
        })
        api1 = r.json()
        
        r = await c.post("/api-catalog/", json={
            "name": "API2",
            "base_url": "https://api.example.com",
            "method": "POST",
            "path": "/v2",
            "description": "API2",
            "headers": {},
            "body_schema": {},
            "auth_type": "none",
            "timeout_ms": 30000
        })
        api2 = r.json()
        
        # Create chain
        r = await c.post("/api-catalog/chains", json={
            "name": "Test Chain",
            "description": "API1 -> API2",
            "members": [
                {"order": 1, "api_id": api1["id"], "input_mapping": {"q": "{{query}}"}},
                {"order": 2, "api_id": api2["id"], "input_mapping": {"data": "{{step1.data}}"}}
            ]
        })
        assert r.status_code == 200
        chain = r.json()
        print(f"  CREATE: OK ({chain['name']}, steps={chain['steps_count']})")
        
        # Get chain
        r = await c.get(f"/api-catalog/chains/{chain['id']}")
        assert r.status_code == 200 and r.json()["name"] == "Test Chain"
        assert r.json()["steps_count"] == 2
        assert len(r.json()["members"]) == 2
        print("  GET: OK (steps=2, members=2)")
        
        # List chains
        r = await c.get("/api-catalog/chains")
        assert r.status_code == 200 and len(r.json()) == 1
        print("  LIST: OK")
        
        # Execute chain
        r = await c.post(f"/api-catalog/chains/{chain['id']}/execute", json={
            "input_data": {"query": "test"}
        })
        assert r.status_code == 200
        print(f"  EXECUTE: OK (status={r.json().get('status')})")
        
        # Delete chain
        r = await c.delete(f"/api-catalog/chains/{chain['id']}")
        assert r.status_code == 200
        r = await c.get("/api-catalog/chains")
        assert len(r.json()) == 0
        print("  DELETE: OK")
        
        # Cleanup
        await c.delete(f"/api-catalog/{api1['id']}")
        await c.delete(f"/api-catalog/{api2['id']}")
    
    print()
    print("=" * 50)
    print("TEST 3: Frontend Verification")
    print("=" * 50)
    
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3000", timeout=10) as c:
        # Check nav has API link
        r = await c.get("/")
        html = r.text
        assert "/api-catalog" in html, "Nav missing /api-catalog link"
        print("  Nav: /api-catalog link found")
        
        # Check page renders
        r = await c.get("/api-catalog")
        html = r.text
        assert "page.tsx" in html or "api-catalog/page.js" in html
        print("  Page: JS chunk loaded")
        
        # Check CSS
        assert "api-catalog/page.css" in html
        print("  CSS: page.module.css loaded")
        
    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)

asyncio.run(test_all())
