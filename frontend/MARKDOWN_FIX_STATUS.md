# Markdown 渲染问题诊断

## 当前状态（问题）
- `### **总结**` 显示为纯文本（未渲染为标题）
- ` ```python ` 显示为纯文本（未渲染为代码块）
- 所有 Markdown 语法原样显示

## 已做的修复
1. ✅ `_normalize_markdown` - 后端单行压缩文本规范化
2. ✅ `ensureNewlines` / `restoreMarkdownNewlines` - 前端 Markdown 格式化
3. ✅ CSS 深色主题代码块样式 + 语言标签
4. ✅ rehype-highlight 配色方案（GitHub Dark 风格）

## 待修复
- [x] 后端 `chat.py` 在保存前调用 `_normalize_markdown`
- [ ] 确保 LLM 返回 Markdown 时包含正确换行
