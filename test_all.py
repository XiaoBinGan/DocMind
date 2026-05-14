import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:8000"
results = []

def test(name, success, details=""):
    status = "PASS" if success else "FAIL"
    results.append(f"[{status}] {name}: {details if details else 'OK'}")

print("=" * 60)
print("DocMind 全功能测试")
print("=" * 60)

# 1. Health check
try:
    r = requests.get(f"{BASE}/health", timeout=5)
    test("Health", r.status_code == 200, r.json().get("status"))
except Exception as e:
    test("Health", False, str(e))

# 2. Register new user
token = None
try:
    r = requests.post(f"{BASE}/api/auth/register", json={
        "username": "finaltest99",
        "password": "Test123456",
        "email": "final99@dm.com"
    }, timeout=10)
    if r.status_code == 201:
        token = r.json()["token"]
        test("注册", True, f"user={r.json()['user']['username']}")
    elif r.status_code == 400 and "taken" in r.json().get("detail", ""):
        # 已存在则登录
        r = requests.post(f"{BASE}/api/auth/login", json={
            "username": "finaltest99",
            "password": "Test123456"
        }, timeout=10)
        if r.status_code == 200:
            token = r.json()["token"]
            test("注册/登录", True, f"user={r.json()['user']['username']} (已存在)")
        else:
            test("注册/登录", False, r.json().get("detail"))
    else:
        test("注册", False, r.json().get("detail"))
except Exception as e:
    test("注册", False, str(e))

# 3. Login
try:
    r = requests.post(f"{BASE}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    }, timeout=10)
    if r.status_code == 200:
        token = r.json()["token"]
        test("登录", True, f"user={r.json()['user']['username']} is_admin={r.json()['user']['is_admin']}")
    else:
        test("登录", False, r.json().get("detail"))
except Exception as e:
    test("登录", False, str(e))

# 4. Document list
if token:
    try:
        r = requests.get(f"{BASE}/api/documents", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            docs = r.json()["documents"]
            test("文档列表", True, f"total={r.json()['total']}")
        else:
            test("文档列表", False, r.json().get("detail"))
    except Exception as e:
        test("文档列表", False, str(e))

# 5. Create conversation
conv_id = None
if token:
    try:
        r = requests.post(f"{BASE}/api/conversations", json={
            "title": "全功能测试对话",
            "chat_type": "doc_chat"
        }, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            conv_id = r.json()["id"]
            test("创建对话", True, f"id={conv_id[:12]}... type={r.json()['chat_type']}")
        else:
            test("创建对话", False, f"{r.status_code} {r.json().get('detail')}")
    except Exception as e:
        test("创建对话", False, str(e))

# 6. List conversations
if token and conv_id:
    try:
        r = requests.get(f"{BASE}/api/conversations", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            test("对话列表", True, f"total={r.json()['total']}")
        else:
            test("对话列表", False, r.json().get("detail"))
    except Exception as e:
        test("对话列表", False, str(e))

# 7. Send message (non-streaming)
if token and conv_id:
    try:
        r = requests.post(f"{BASE}/api/chat", json={
            "message": "你好，请简单介绍一下你自己",
            "conversation_id": conv_id
        }, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r.status_code == 200:
            resp_data = r.json()
            if "message" in resp_data and "content" in resp_data["message"]:
                resp = resp_data["message"]["content"][:120] + ".."
                test("聊天(非流式)", True, resp)
            else:
                test("聊天(非流式)", False, f"响应格式异常: {list(resp_data.keys())}")
        else:
            test("聊天(非流式)", False, f"{r.status_code} {r.json().get('detail')}")
    except Exception as e:
        test("聊天(非流式)", False, str(e))

# 8. Chat stream (fixed SSE parsing)
if token and conv_id:
    try:
        r = requests.post(f"{BASE}/api/chat/stream", json={
            "message": "用一句话介绍AI",
            "conversation_id": conv_id
        }, headers={"Authorization": f"Bearer {token}"}, timeout=120, stream=True)
        if r.status_code == 200:
            full = ""
            for line in r.iter_lines():
                if line:
                    text = line.decode('utf-8').strip()
                    if text.startswith("data: "):
                        try:
                            data = json.loads(text[6:])
                            full += data
                        except:
                            full += text[6:]
            test("聊天(流式)", True, f"received={len(full)} chars: {full[:60]}..")
        else:
            test("聊天(流式)", False, f"{r.status_code}")
    except Exception as e:
        test("聊天(流式)", False, str(e))

# 9. Settings
if token:
    try:
        r = requests.get(f"{BASE}/api/settings", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            if isinstance(r.json(), dict):
                test("系统设置", True, f"keys={list(r.json().keys())[:5]}")
            else:
                test("系统设置", False, f"返回类型错误: {type(r.json())}")
        else:
            test("系统设置", False, r.json().get("detail"))
    except Exception as e:
        test("系统设置", False, str(e))

# 10. Memories
if token:
    try:
        r = requests.get(f"{BASE}/api/memories", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, dict) and "total" in data:
                    test("记忆列表", True, f"total={data['total']}")
                else:
                    test("记忆列表", False, f"响应格式异常: {data}")
            except:
                test("记忆列表", False, f"非JSON响应: {r.text[:200]}")
        else:
            test("记忆列表", False, f"{r.status_code} {r.json().get('detail')}")
    except Exception as e:
        test("记忆列表", False, str(e))

# 11. Memory create
if token:
    try:
        r = requests.post(f"{BASE}/api/memories", json={
            "content": "全功能测试记忆",
            "category": "daily",
            "importance": 5
        }, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 201:
            test("记忆创建", True, f"id={r.json()['id'][:12]}")
            # Delete it
            requests.delete(f"{BASE}/api/memories/{r.json()['id']}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        else:
            test("记忆创建", False, f"{r.status_code} {r.json().get('detail')}")
    except Exception as e:
        test("记忆创建", False, str(e))

# 12. Document detail
if token:
    try:
        r = requests.get(f"{BASE}/api/documents", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            doc_id = r.json()["documents"][0]["id"] if r.json()["documents"] else None
            if doc_id:
                r2 = requests.get(f"{BASE}/api/documents/{doc_id}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
                if r2.status_code == 200:
                    test("文档详情", True, f"文件={r2.json()['name'][:30]}")
                else:
                    test("文档详情", False, f"{r2.status_code}")
            else:
                test("文档详情", True, "无文档")
        else:
            test("文档详情", False, r.json().get("detail"))
    except Exception as e:
        test("文档详情", False, str(e))

# Print results
print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)
for res in results:
    print(res)
passed = sum(1 for res in results if res.startswith('[PASS]'))
failed = sum(1 for res in results if res.startswith('[FAIL]'))
print(f"\n总计: {len(results)} 项 | 通过: {passed} | 失败: {failed}")
print("=" * 60)
