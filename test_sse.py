"""Test the full SSE flow of chat_stream endpoint."""
import asyncio
import aiohttp
import json

URL = "http://localhost:8000/api/chat/stream"

async def test():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            URL,
            json={
                "message": "请用markdown写一段介绍：标题、一段文字、一个python代码块、一个表格。",
                "stream": True
            },
            headers={"Content-Type": "application/json"}
        ) as resp:
            print(f"Status: {resp.status}")
            print(f"Content-Type: {resp.content_type}")
            print("=" * 60)
            
            raw_text = ""
            full_content = None
            
            async for line in resp.content:
                text = line.decode("utf-8").strip()
                if not text:
                    continue
                if text.startswith("event:"):
                    event = text[6:].strip()
                    continue
                if text.startswith("data:"):
                    data = text[5:].strip()
                    event_type = locals().get("_event", "")
                    
                    if event_type == "chunk":
                        # JSON-encoded chunk
                        try:
                            chunk = json.loads(data)
                            raw_text += chunk
                            print(f"[chunk] len={len(chunk)} repr={repr(chunk)[:50]}")
                        except:
                            raw_text += data
                    
                    elif event_type == "full_content":
                        full_content = json.loads(data)
                        print(f"[full_content] len={len(full_content)}")
                        print("-" * 40)
                        print(full_content)
                        print("-" * 40)
                    
                    elif event_type == "done":
                        print(f"[done] messageId={data}")
                    
                    elif event_type == "intent":
                        intent = json.loads(data)
                        print(f"[intent] type={intent.get('intent_type')}")
                
                # Track current event
                pass  # already handled above

            # Summary
            print(f"\n=== 原始累积文本 ===")
            print(repr(raw_text))
            print(f"换行数: {raw_text.count(chr(10))}")
            
            if full_content:
                print(f"\n=== 格式化完整文本 ===")
                print(full_content)
                print(f"换行数: {full_content.count(chr(10))}")

asyncio.run(test())
