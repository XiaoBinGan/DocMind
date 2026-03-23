# DocMind — 推理式文档智能问答

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-00C9FF?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js" alt="Next.js">
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License">
</p>

> 🧠 **DocMind** — 基于 PageIndex 思想的推理式 RAG 系统，让 AI 像专家一样阅读文档。告别向量相似度，拥抱真正的相关性。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔮 **PageIndex 推理式检索** | 不依赖向量相似度，让 LLM 自主遍历索引树推理答案 |
| 📑 **Marker 高质量解析** | PDF → Markdown，保留标题层级、表格、公式、代码块 |
| 🌳 **智能索引树** | 自动从 Markdown 结构构建 ToC 树，模拟人读文档方式 |
| 💬 **RAG 对话** | 基于文档内容的精准问答，支持流式输出 |
| 🤖 **多模型支持** | OpenAI / Anthropic / Qwen / 本地模型，可配置 |
| 🎨 **深海洞穴主题** | Deep Ocean UI，沉浸式视觉体验 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────┐
│                      前端 (Next.js)                    │
│   首页 │ 文档管理 │ RAG 对话 │ 索引树 │ 设置          │
└──────────────┬──────────────────────────────────────┘
               │ HTTP / SSE
┌──────────────▼──────────────────────────────────────┐
│                   后端 (FastAPI)                      │
│                                                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Parser   │→ │  PageIndexer │→ │  PageRetriever│   │
│  │ (Marker) │  │  (构建索引树) │  │  (推理检索)   │   │
│  └──────────┘  └──────────────┘  └──────────────┘   │
│                                           │           │
│                                    ┌──────▼──────┐    │
│                                    │  LLM Service │    │
│                                    │ (OpenAI/Qwen)│    │
│                                    └─────────────┘     │
└──────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
docmind/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── routers/            # API 路由
│   │   │   ├── documents.py    # 文档管理 API
│   │   │   └── chat.py        # RAG 对话 API
│   │   ├── services/          # 核心服务 ⭐
│   │   │   ├── parser.py      # 文档解析 (Marker / PyPDF2)
│   │   │   ├── indexer.py     # PageIndex 索引构建
│   │   │   └── llm.py         # LLM 调用封装
│   │   ├── models/             # SQLAlchemy 数据模型
│   │   └── core/               # 配置管理
│   ├── uploads/                # 上传文件存储
│   ├── .venv/                 # Python 虚拟环境
│   └── run.py                 # 启动入口
│
└── frontend/                   # Next.js 前端
    ├── app/
    │   ├── page.tsx            # 首页
    │   ├── documents/          # 文档管理页面
    │   ├── chat/              # RAG 对话页面
    │   ├── index-tree/        # 索引树可视化
    │   └── settings/          # 模型配置
    └── lib/
        └── api.ts            # API 调用封装
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- npm / pnpm

### 1. 克隆 & 进入目录

```bash
git clone https://github.com/XiaoBinGan/DocMind.git
cd DocMind
```

### 2. 配置后端

```bash
cd backend
cp .env.example .env
```

编辑 `.env`：

```env
# LLM 提供商 (openai / anthropic / qwen)
LLM_PROVIDER=openai

# API Keys
OPENAI_API_KEY=sk-your-openai-key
# ANTHROPIC_API_KEY=sk-ant-your-key
# DASHSCOPE_API_KEY=your-dashscope-key

# 模型配置
MODEL_NAME=gpt-4o-mini
```

### 3. 安装依赖

```bash
# 后端（推荐使用虚拟环境）
cd backend
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 4. 启动服务

```bash
# 终端 1: 后端 (端口 8000)
cd backend
source .venv/bin/activate
python run.py

# 终端 2: 前端 (端口 3000)
cd frontend
npm run dev
```

### 5. 打开浏览器

访问 **http://localhost:3000**

---

## 🔧 配置说明

### 支持的 LLM 提供商

| 提供商 | 环境变量 | 模型示例 |
|--------|---------|---------|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet` |
| 通义千问 | `DASHSCOPE_API_KEY` | `qwen-plus`, `qwen-max` |

在设置页面可动态切换，无需重启服务。

### PDF 解析引擎

系统自动检测并使用以下引擎（按优先级）：

1. **Marker** — PDF → 高质量 Markdown（标题层级、表格、公式、代码块）
2. **PyPDF2** — 纯文本提取（降级方案）

Marker 模型首次运行自动下载（约 3GB，缓存到 `~/Library/Caches/datalab`）。

---

## 🧠 PageIndex 原理

### 传统 RAG 的痛点

```
向量相似度 ≠ 语义相关性

用户问："第三章讲了什么？"
向量检索 → 找到"第三章"附近文字 → 答非所问
```

### DocMind 的解决思路

```
Step 1: 构建索引树
  Markdown 结构 → 自动识别 # ## ### 标题
  → 生成 ToC 树（带页码范围）

Step 2: 推理检索
  用户问题 → LLM 分析需要哪些章节
  → 遍历索引树选择节点 → 提取上下文

Step 3: 生成回答
  上下文 + 问题 → LLM → 精准回答
```

> 核心思想：模拟人读文档的方式——先看目录，再定位内容。

---

## 📡 API 文档

### 文档管理

```
POST   /api/documents/upload          上传文档
GET    /api/documents                列出所有文档
GET    /api/documents/{id}          获取文档详情
GET    /api/documents/{id}/index    获取索引树
DELETE /api/documents/{id}          删除文档
POST   /api/documents/{id}/reindex  重建索引
```

### RAG 对话

```
POST   /api/chat                    发送消息（非流式）
POST   /api/chat/stream             流式对话（SSE）
GET    /api/conversations           列出会话列表
DELETE /api/conversations/{id}      删除会话
```

---

## 🛠️ 扩展开发

### 添加新文档格式

编辑 `backend/app/services/parser.py`：

```python
@staticmethod
async def _parse_xxx(file_path: str) -> dict:
    # 1. 解析文件
    # 2. 提取页面内容
    # 3. 返回标准化结构
    return {
        "success": True,
        "page_count": len(pages),
        "pages": [{"page_number": i, "content": "...", "char_count": n}],
        "title": "文档标题",
        "parser": "your_parser"
    }
```

然后在 `SUPPORTED_TYPES` 和 `parse()` 方法中添加分支。

### 添加新 LLM 提供商

编辑 `backend/app/services/llm.py`，实现 `generate()` 方法即可。

---

## 📦 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 15, React 19, TypeScript, Tailwind CSS, Zustand |
| **后端** | FastAPI 0.109, SQLAlchemy, aiosqlite, Pydantic |
| **文档解析** | Marker (PDF→Markdown), PyPDF2, python-docx |
| **LLM** | OpenAI SDK, Anthropic SDK, 通义千问 SDK |
| **部署** | 单机运行，支持 Docker（可选） |

---

## ⚠️ 常见问题

**Q: PDF 解析失败？**  
A: 确保 Marker 模型已下载，或检查 PDF 是否为扫描件（需 OCR）。

**Q: 模型调用报 401？**  
A: 检查 `.env` 中的 API Key 是否正确、是否过期。

**Q: 上传大文件超时？**  
A: 修改 `backend/app/core/config.py` 中的 `UPLOAD_MAX_SIZE` 和 uvicorn 超时配置。

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  <em>DocMind — 让 AI 像专家一样阅读文档</em>
</p>
