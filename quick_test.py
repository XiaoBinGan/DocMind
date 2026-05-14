import httpx
import asyncio
import json

async def test():
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Login
        r = await client.post("http://localhost:8000/api/auth/login", 
            json={"username": "admin", "password": "admin123"})
        token = r.json()["token"]
        print(f"Login: {r.status_code}")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Check token summary
        r = await client.get("http://localhost:8000/api/token/my-summary", headers=headers)
        print(f"\nToken Summary: {r.status_code}")
        print(f"Data: {json.dumps(r.json(), indent=2)}")
        
        # 3. Check token usage records
        r = await client.get("http://localhost:8000/api/token/my-usage", headers=headers)
        print(f"\nToken Usage: {r.status_code}")
        print(f"Records: {len(r.json())} records")
        if r.json():
            print(f"First: {json.dumps(r.json()[0], indent=2)}")
        
        # 4. Check admin token summary
        r = await client.get("http://localhost:8000/api/token/admin/summary", headers=headers)
        print(f"\nAdmin Summary: {r.status_code}")
        print(f"Data: {json.dumps(r.json(), indent=2)}")

asyncio.run(test())
