# API 目录系统 — 部署与使用指南

## 📦 已完成文件清单

### 后端（Python/FastAPI）

| 文件 | 作用 |
|---|---|
| `backend/app/models/database.py` | 新增 4 个模型：ApiDefinition, SerialChain, SerialChainMember, ApiUsageLog |
| `backend/app/models/schemas.py` | 新增 11 个 Pydantic schema |
| `backend/app/services/api_catalog.py` | API CRUD + 调用日志 |
| `backend/app/services/serial_chain.py` | 串行链路 CRUD + 执行引擎（含占位符解析） |
| `backend/app/services/intent_analyzer.py` | AI 意图分析（注入 API 目录到 Prompt） |
| `backend/app/routers/api_catalog.py` | 6 个 CRUD 端点 |
| `backend/app/routers/serial_chain.py` | 6 个端点（含 execute） |

### 前端（Next.js）

| 文件 | 作用 |
|---|---|
| `frontend/app/api-catalog/page.tsx` | API 目录管理页 |
| `frontend/components/api-catalog/api-card.tsx` | API 卡片组件 |
| `frontend/components/api-catalog/api-form.tsx` | 多步注册表单 |
| `frontend/lib/api-catalog.ts` | API client（CRUD + toggle） |
| `frontend/app/chains/page.tsx` | 串行链路管理页 |
| `frontend/app/api-test/page.tsx` | API 在线测试工具 |
| `frontend/components/chains/chain-editor.tsx` | 链路编辑器 |
| `frontend/components/chains/chain-preview.tsx` | 链路预览组件 |
| `frontend/components/chat/api-suggestion-card.tsx` | 聊天中 API 建议组件 |
| `frontend/lib/chains.ts` | 链路 API client |

## 🚀 部署步骤

### 1. 更新 main.py 路由注册

在 `backend/app/main.py` 的 import 和路由注册部分追加：

```python
from app.routers import api_catalog, serial_chain  # 新增

# ... 在路由注册部分追加 ...
app.include_router(api_catalog.router)
app.include_router(serial_chain.router)
```

### 2. 重启后端

```bash
cd backend
python run.py
```

### 3. 验证 API 端点

```bash
# 先登录获取 token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'

# 注册 API
curl -X POST http://localhost:8000/api/api-catalog \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "创建用户",
    "api_type": "REST",
    "url": "https://api.example.com/users",
    "method": "POST"
  }'
```

## 📋 API 端点总览

### API 目录

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/api-catalog` | 列出所有启用 API |
| GET | `/api/api-catalog/:id` | 获取详情 |
| POST | `/api/api-catalog` | 注册 API |
| PUT | `/api/api-catalog/:id` | 更新 API |
| DELETE | `/api/api-catalog/:id` | 删除 API |
| POST | `/api/api-catalog/:id/toggle` | 启用/禁用 |
| GET | `/api/api-catalog/usage-logs` | 调用日志 |

### 串行链路

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/serial-chains` | 列出链路 |
| GET | `/api/serial-chains/:id` | 获取详情 |
| POST | `/api/serial-chains` | 创建链路 |
| PUT | `/api/serial-chains/:id` | 更新链路 |
| DELETE | `/api/serial-chains/:id` | 删除链路 |
| POST | `/api/serial-chains/:id/execute` | 执行链路 |

## 🔧 下一步

- [ ] 集成 IntentAnalyzer 到 chat.py
- [ ] 前端导航菜单添加 API 管理入口
- [ ] API 测试页集成 API 目录列表
