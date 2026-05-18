"use client"

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SAMPLE = `# 测试标题

## 二级标题

这是**加粗**和*斜体*。

- 列表项 A
- 列表项 B

| 列1 | 列2 |
|---|---|
| A | B |

\`\`\`python
def hello():
    print("Hello!")
\`\`\`
`

export default function Page() {
  const [raw] = useState(SAMPLE)
  
  return (
    <div style={{ padding: 40, background: '#111', color: '#fff', minHeight: '100vh' }}>
      <h1>Markdown 测试</h1>
      
      <h2>渲染结果：</h2>
      <div style={{ background: '#1a1f2e', padding: 20, borderRadius: 8 }}>
        <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]}>
          {raw}
        </ReactMarkdown>
      </div>
      
      <h2>原始内容：</h2>
      <pre style={{ background: '#222', padding: 20, whiteSpace: 'pre-wrap' }}>
        {raw}
      </pre>
    </div>
  )
}
