import requests
import json

BASE = "http://127.0.0.1:8000"

# 1. 创建一个真实的 API 定义
api_resp = requests.post(f"{BASE}/api-catalog/", json={
    "name": "天气查询API",
    "description": "通过经纬度获取天气信息",
    "base_url": "https://api.open-meteo.com",
    "method": "GET",
    "path": "/v1/forecast",
    "headers": {},
    "body_schema": {},
    "auth_type": "none",
    "timeout_ms": 30000,
    "enabled": True,
    "example_queries": ["查询天气", "今天天气怎么样", "明天温度"],
    "expected_response": '{"latitude": 31.23, "longitude": 121.47, "current_weather": {...}}'
})
api_id = api_resp.json()["id"]
print(f"API 创建成功: {api_resp.json()['name']} (ID: {api_id})")

# 2. 创建一条链
chain_resp = requests.post(f"{BASE}/api-catalog/chains", json={
    "name": "天气查询链",
    "description": "查询指定城市的天气",
    "members": [
        {
            "order": 1,
            "api_id": api_id,
            "input_mapping": {
                "latitude": "$.lat",
                "longitude": "$.lon",
                "current": "true"
            },
            "output_mapping": {
                "temperature": "$.current_weather.temperature",
                "windspeed": "$.current_weather.windspeed",
                "weather_code": "$.current_weather.weathercode"
            }
        }
    ]
})
chain_id = chain_resp.json()["id"]
print(f"链创建成功: {chain_resp.json()['name']} (ID: {chain_id})")

# 3. 执行链
exec_resp = requests.post(f"{BASE}/api-catalog/chains/{chain_id}/execute", json={
    "input_data": {
        "lat": 31.23,
        "lon": 121.47
    }
})
print(f"\n执行结果:")
print(json.dumps(exec_resp.json(), indent=2, ensure_ascii=False))
