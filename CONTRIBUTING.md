# 贡献指南

感谢你对 DocMind 的兴趣！本文档提供了如何为项目做出贡献的指导。

## 开始前

- 阅读 [README.md](README.md) 了解项目概况
- 遵守 [行为准则](CODE_OF_CONDUCT.md)
- 检查 [Issues](https://github.com/XiaoBinGan/DocMind/issues) 和 [Discussions](https://github.com/XiaoBinGan/DocMind/discussions)，避免重复工作

## 开发环境设置

### 后端开发

```bash
# 克隆仓库
git clone https://github.com/XiaoBinGan/DocMind.git
cd DocMind/backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
pip install -e .  # 开发模式

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key

# 运行测试
pytest

# 启动开发服务器
python run.py
```

### 前端开发

```bash
# 进入前端目录
cd DocMind/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 运行 linter
npm run lint
```

## 提交流程

### 1. 创建 Issue

在开始工作前，请先创建或评论相关 Issue：

```markdown
**标题**：简洁描述问题或功能

**描述**：
- 问题背景
- 期望的解决方案
- 相关的 Issue 或 PR

**标签**：bug / feature / documentation / help wanted
```

### 2. Fork 和克隆

```bash
# Fork 项目到你的账户
# 克隆你的 fork
git clone https://github.com/YOUR_USERNAME/DocMind.git
cd DocMind

# 添加上游远程
git remote add upstream https://github.com/XiaoBinGan/DocMind.git
```

### 3. 创建特性分支

```bash
# 更新本地 main
git fetch upstream
git checkout main
git merge upstream/main

# 创建特性分支
git checkout -b feature/your-feature-name
```

**分支命名规范**：
- `feature/` - 新功能
- `fix/` - Bug 修复
- `docs/` - 文档更新
- `refactor/` - 代码重构
- `test/` - 测试相关
- `chore/` - 构建、依赖等

### 4. 提交更改

```bash
# 查看更改
git status
git diff

# 暂存更改
git add .

# 提交更改（遵循 Conventional Commits）
git commit -m "type(scope): description"
```

**提交消息格式**：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档
- `style`: 代码风格（不影响功能）
- `refactor`: 代码重构
- `perf`: 性能改进
- `test`: 测试
- `chore`: 构建、依赖等

**示例**：
```
feat(chat): 添加流式输出支持

- 实现 SSE 流式响应
- 优化前端消息显示
- 添加加载动画

Closes #123
```

### 5. 推送和创建 PR

```bash
# 推送到你的 fork
git push origin feature/your-feature-name

# 在 GitHub 上创建 Pull Request
```

**PR 模板**：

```markdown
## 描述
简洁描述你的更改

## 相关 Issue
Closes #123

## 更改类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 破坏性更改
- [ ] 文档更新

## 测试
- [ ] 添加了测试
- [ ] 所有测试通过
- [ ] 手动测试通过

## 检查清单
- [ ] 代码遵循项目风格
- [ ] 自我审查了代码
- [ ] 添加了必要的注释
- [ ] 更新了相关文档
- [ ] 没有新的警告
```

## 代码风格

### Python

```bash
# 使用 Black 格式化
pip install black
black .

# 使用 Flake8 检查
pip install flake8
flake8 .

# 使用 isort 排序导入
pip install isort
isort .
```

### TypeScript/JavaScript

```bash
# 使用 Prettier 格式化
npm install --save-dev prettier
npx prettier --write .

# 使用 ESLint 检查
npm run lint
```

## 测试

### 后端测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_parser.py

# 生成覆盖率报告
pytest --cov=app tests/
```

### 前端测试

```bash
# 运行测试
npm test

# 生成覆盖率报告
npm test -- --coverage
```

## 文档

- 在代码中添加清晰的注释
- 更新 README 中的相关部分
- 为新功能添加 API 文档
- 提供使用示例

## 常见问题

**Q: 我应该在哪里开始？**
A: 查看标有 `good first issue` 或 `help wanted` 的 Issue。

**Q: 如何报告 Bug？**
A: 创建一个 Issue，包含复现步骤、预期行为和实际行为。

**Q: 我的 PR 被拒绝了怎么办？**
A: 这很正常！仔细阅读反馈，进行必要的更改，然后重新提交。

**Q: 多久会收到 PR 审查？**
A: 通常在 1-3 天内，取决于维护者的可用性。

## 获得帮助

- 📖 查看 [文档](README.md)
- 💬 在 [Discussions](https://github.com/XiaoBinGan/DocMind/discussions) 中提问
- 📧 发送邮件至 [solitaryhao8@gmail.com](mailto:solitaryhao8@gmail.com)
- 🐦 在 Twitter 上关注 [@DocMindAI](https://twitter.com/DocMindAI)

---

**感谢你的贡献！** 🎉
