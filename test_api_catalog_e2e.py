"""Test all /api-catalog endpoints."""
import asyncio
import httpx
import sys

BASE = "http://localhost:8000/api-catalog"

async def test():
    async with httpx.AsyncClient(timeout=10) as client:
        # Test /apis (list all)
        print("=== GET /apis ===")
        r = await client.get(f"{BASE}/apis")
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:200]}")
        print()
        
        # Test / (list all)
        print("=== GET / ===")
        r = await client.get(f"{BASE}/")
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:200]}")
        print()
        
        # Test /chains (list all chains)
        print("=== GET /chains ===")
        r = await client.get(f"{BASE}/chains")
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:500]}")
        print()
        
        # Test /chains/{id}
        print("=== GET /chains/{id} ===")
        if r.status_code == 200 and r.json():
            chain_id = r.json()[0]["id"]
            r = await client.get(f"{BASE}/chains/{chain_id}")
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:500]}")
            print()
        
        # Test nonexistent /{api_id}
        print("=== GET /{nonexistent_id} ===")
        r = await client.get(f"{BASE}/00000000-0000-0000-0000-000000000000")
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:200]}")
        print()
        
        # Test POST / (create API)
        print("=== POST / ===")
        create_data = {
            "name": "Test API",
            "description": "Test for validation",
            "base_url": "https://api.example.com",
            "method": "GET",
            "path": "/test",
            "headers": {},
            "body_schema": {},
            "auth_type": "none"
        }
        r = await client.post(f"{BASE}/", json=create_data)
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:500]}")
        if r.status_code == 200:
            new_api_id = r.json()["id"]
            print()
            
            # Get it
            print("=== GET /{id} ===")
            r = await client.get(f"{BASE}/{new_api_id}")
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:200]}")
            print()
            
            # Update it
            print("=== PUT /{id} ===")
            r = await client.put(f"{BASE}/{new_api_id}", json={"description": "Updated test"})
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:200]}")
            print()
            
            # Toggle it
            print("=== PATCH /{id}/toggle ===")
            r = await client.patch(f"{BASE}/{new_api_id}/toggle", params={"enabled": False})
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:200]}")
            print()
            
            # Delete it
            print("=== DELETE /{id} ===")
            r = await client.delete(f"{BASE}/{new_api_id}")
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:200]}")
            print()
            
            # Verify deleted (should 404)
            print("=== GET /{id} after delete (expect 404) ===")
            r = await client.get(f"{BASE}/{new_api_id}")
            print(f"Status: {r.status_code}")
            print()

        # Test POST /chains (create chain)
        print("=== POST /chains ===")
        # First list APIs for chain members
        r = await client.get(f"{BASE}/")
        if r.status_code == 200 and r.json():
            api_id = r.json()[0]["id"]
            chain_data = {
                "name": "Test Chain",
                "description": "Test chain for validation",
                "members": [
                    {"order": 1, "api_id": api_id, "input_mapping": {}, "output_mapping": {}}
                ]
            }
            r = await client.post(f"{BASE}/chains", json=chain_data)
            print(f"Status: {r.status_code}")
            print(f"Body: {r.text[:500]}")
            if r.status_code == 200:
                chain_id = r.json()["id"]
                
                # Execute
                print("=== POST /chains/{id}/execute ===")
                r = await client.post(f"{BASE}/chains/{chain_id}/execute", json={"input_data": {"url": "https://example.com"}})
                print(f"Status: {r.status_code}")
                print(f"Body: {r.text[:500]}")
                print()

asyncio.run(test())
