"""Quick test for chain CRUD after route order fix."""
import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10) as c:
        # 1. LIST chains (should be 200, empty)
        print("=== LIST (before) ===")
        r = await c.get("/api-catalog/chains")
        print(f"Status: {r.status_code}, Count: {len(r.json())}")

        # 2. CREATE a chain
        print("\n=== CREATE ===")
        body = {
            "name": "Test Chain",
            "description": "Test chain for verification",
            "members": [
                {"order": 1, "api_id": "00000000-0000-0000-0000-000000000000", "input_mapping": {}, "output_mapping": {}}
            ]
        }
        r = await c.post("/api-catalog/chains", json=body)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Name: {data['name']}, Members: {len(data['members'])}")
            chain_id = data["id"]
        else:
            print(f"Error: {r.text[:300]}")
            chain_id = None

        # 3. LIST chains (should be 200, 1)
        print("\n=== LIST (after create) ===")
        r2 = await c.get("/api-catalog/chains")
        print(f"Status: {r2.status_code}, Count: {len(r2.json())}")

        # 4. GET chain
        if chain_id:
            print("\n=== GET ===")
            r3 = await c.get(f"/api-catalog/chains/{chain_id}")
            print(f"Status: {r3.status_code}, Name: {r3.json().get('name', 'N/A')}")

        # 5. DELETE chain
        if chain_id:
            print("\n=== DELETE ===")
            r4 = await c.delete(f"/api-catalog/chains/{chain_id}")
            print(f"Status: {r4.status_code}, Body: {r4.text}")

        # 6. LIST chains (should be empty again)
        print("\n=== LIST (after delete) ===")
        r5 = await c.get("/api-catalog/chains")
        print(f"Status: {r5.status_code}, Count: {len(r5.json())}")

        # 7. GET nonexistent chain
        print("\n=== GET nonexistent ===")
        r6 = await c.get("/api-catalog/chains/00000000-0000-0000-0000-000000000000")
        print(f"Status: {r6.status_code}, Body: {r6.text[:200]}")

        # 8. Test API endpoints still work
        print("\n=== API CREATE (valid) ===")
        body2 = {
            "name": "Test API",
            "description": "test",
            "base_url": "http://example.com",
            "method": "GET",
        }
        r7 = await c.post("/api-catalog/", json=body2)
        print(f"Status: {r7.status_code}")
        if r7.status_code == 200:
            api_id = r7.json()["id"]
            print(f"GET by ID: ", end="")
            r8 = await c.get(f"/api-catalog/{api_id}")
            print(f"Status: {r8.status_code}, Name: {r8.json().get('name', 'N/A')}")
            # Cleanup
            await c.delete(f"/api-catalog/{api_id}")

if __name__ == "__main__":
    asyncio.run(main())
