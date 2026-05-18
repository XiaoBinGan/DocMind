"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import { rehypeAddLanguageLabels } from "../components/chat/rehype-add-language-labels"

const TEST_MARKDOWN = `# Heading 1

## Heading 2

**Bold text** and *italic text*

- List item 1
- List item 2

| Col1 | Col2 |
|------|------|
| A    | B    |

\`\`\`python
def hello():
    print("Hello, World!")
\`\`\`

> This is a blockquote

\`inline code\`

---

Regular paragraph with **bold** and [a link](https://example.com).
`

export default function TestMdPage() {
  return (
    <div style={{ padding: 40, background: "#0f1e35", minHeight: "100vh" }}>
      <h1 style={{ color: "#00c9ff" }}>Markdown 渲染测试</h1>
      
      <h2 style={{ color: "#fff" }}>测试 1: 只有 remarkGfm</h2>
      <div style={{ background: "#1a1f2e", padding: 20, borderRadius: 8, marginBottom: 20 }}>
        <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]}>
          {TEST_MARKDOWN}
        </ReactMarkdown>
      </div>
      
      <h2 style={{ color: "#fff" }}>测试 2: 有 remarkGfm + rehypeHighlight</h2>
      <div style={{ background: "#1a1f2e", padding: 20, borderRadius: 8, marginBottom: 20 }}>
        <ReactMarkdown
          remarkPlugins={[[remarkGfm, { singleTilde: false }]]}
          rehypePlugins={[[rehypeHighlight], rehypeAddLanguageLabels]}
        >
          {TEST_MARKDOWN}
        </ReactMarkdown>
      </div>
      
      <h2 style={{ color: "#fff" }}>原始 Markdown：</h2>
      <pre style={{ background: "#222", padding: 20, whiteSpace: "pre-wrap", color: "#0f0" }}>
        {TEST_MARKDOWN}
      </pre>
    </div>
  )
}
