# 调用链完整流程

## 第 1 步：注册 API 定义
把要调用的外部 API 注册进系统

请求：POST /api-catalog/
```json
{
  "name": "测试API",
  "base_url": "https://httpbin.org",
  "method": "GET",
  "path": "/get",
  "headers": {},
  "body_schema": {},
  "auth_type": "none",
  "timeout_ms": 30000,
  "enabled": true
}
```

## 第 2 步：创建链
把 API 按顺序串联起来

请求：POST /api-catalog/chains
```json
{
  "name": "我的链",
  "members": [
    {
      "order": 1,
      "api_id": "上一步返回的API ID",
      "input_mapping": {
        "url": "$.url"
      },
      "output_mapping": {
        "result": "$.url"
      }
    }
  ]
}
```

## 第 3 步：执行链
传入输入数据，自动按顺序调用

请求：POST /api-catalog/chains/{chain_id}/execute
```json
{
  "input_data": {
    "url": "https://httpbin.org/get?hello=world"
  }
}
```
