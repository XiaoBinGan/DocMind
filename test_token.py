import asyncio
import httpx
import json
import sys

BASE = "http://localhost:8000"

async def test():
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Health
        print("=== 1. Health Check ===")
        r = await client.get(f"{BASE}/api/health")
        print(f"Status: {r.status_code} | Body: {r.text}")
        
        # 2. Register/Login admin
        print("\n=== 2. Login ===")
        r = await client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
        print(f"Status: {r.status_code} | Body: {r.text}")
        if r.status_code == 200:
            token = r.json().get("token", "")
            
            # 3. Get current user
            print("\n=== 3. Current User ===")
            r = await client.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {r.status_code} | Body: {r.text}")
            
            # 4. Create a conversation
            print("\n=== 4. Create Conversation ===")
            r = await client.post(f"{BASE}/api/conversations", json={"title": "Token Test"}, headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {r.status_code} | Body: {r.text}")
            conv_id = ""
            if r.status_code == 200:
                conv_id = r.json().get("id", "")
                
            # 5. Send a chat message
            print("\n=== 5. Send Chat (non-stream) ===")
            r = await client.post(f"{BASE}/api/chat", 
                json={"message": "你好，测试一下 token 记录功能", "conversation_id": conv_id, "stream": False},
                headers={"Authorization": f"Bearer {token}"},
            )
            print(f"Status: {r.status_code} | Body: {r.text[:200]}")
            
            # 6. Check token summary
            print("\n=== 6. Token Summary ===")
            r = await client.get(f"{BASE}/api/token/my-summary?days=30", headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(f"Error: {r.text}")
            
            # 7. Check token usage records
            print("\n=== 7. Token Usage Records ===")
            r = await client.get(f"{BASE}/api/token/my-usage?days=30&limit=10", headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Records count: {len(data)}")
                for rec in data[:3]:
                    print(f"  - {json.dumps(rec, ensure_ascii=False)}")
            else:
                print(f"Error: {r.text}")
                
            # 8. Admin summary
            print("\n=== 8. Admin Token Summary ===")
            r = await client.get(f"{BASE}/api/token/admin/summary?days=30", headers={"Authorization": f"Bearer {token}"})
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Users count: {len(data)}")
                for u in data:
                    print(f"  - {json.dumps(u, ensure_ascii=False)}")
            else:
                print(f"Error: {r.text}")
        else:
            print("Login failed, trying register...")
            r = await client.post(f"{BASE}/api/auth/register", json={"username": "admin", "password": "admin123"})
            print(f"Register Status: {r.status_code} | Body: {r.text}")

asyncio.run(test())
