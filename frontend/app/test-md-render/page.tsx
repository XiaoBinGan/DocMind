"use client"

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'

const SAMPLE = `
## 测试标题

这是一段**加粗**和*斜体*。

- 列表项 1
- 列表项 2

| 名称 | 类型 |
|------|-----|
| A    | B    |

\`\`\`python
def hello():
    print("Hello!")
\`\`\`
`

export default function TestMarkdownPage() {
  const [showRaw, setShowRaw] = useState(false)
  const [showHtml, setShowHtml] = useState(false)
  const [useHighlight, setUseHighlight] = useState(true)
  const [streaming, setStreaming] = useState(false)
  
  const result = streaming ? SAMPLE : processMarkdown(SAMPLE)

  return (
    <div style={{ padding: 40, background: '#111', color: '#fff', minHeight: '100vh' }}>
      <h1>Markdown 渲染测试</h1>
      
      <div style={{ marginBottom: 20, display: 'flex', gap: 10 }}>
        <button onClick={() => setStreaming(!streaming)}>
          {streaming ? '结束流式渲染' : '模拟流式渲染'}
        </button>
        <button onClick={() => setShowRaw(!showRaw)}>
          {showRaw ? '隐藏原始内容' : '显示原始内容'}
        </button>
        <button onClick={() => setShowHtml(!showHtml)}>
          {showHtml ? '隐藏HTML源码' : '显示HTML源码'}
        </button>
        <button onClick={() => setUseHighlight(!useHighlight)}>
          {useHighlight ? '有' : '无'} highlight
        </button>
      </div>

      <h2>渲染结果：</h2>
      <div style={{
        border: '2px solid #00c9ff',
        padding: 20,
        background: '#1a1f2e',
        borderRadius: 8,
        marginBottom: 20
      }}>
        <ReactMarkdown
          remarkPlugins={[[remarkGfm]]}
          rehypePlugins={useHighlight ? [[rehypeHighlight, { detect: true }]] : []}
        >
          {result}
        </ReactMarkdown>
      </div>

      {showRaw && <div>
        <h3>原始 Markdown：</h3>
        <pre style={{ background: '#333', padding: 20, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      </div>}

      {showHtml && <div>
        <h3>HTML 源码：</h3>
        <pre style={{ background: '#333', padding: 20, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12 }}>
          {result}
        </pre>
      </div>}

      <div style={{ marginTop: 30, color: '#999' }}>
        <h3>调试信息：</h3>
        <p>流式渲染: {streaming ? '是' : '否'}</p>
        <p>Highlight: {useHighlight ? '启用' : '禁用'}</p>
        <p>内容长度: {result.length}</p>
      </div>
    </div>
  )
}

function processMarkdown(text: string): string {
  return text
}
