import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import './globals.css'

const sampleMarkdown = `
# Test

## Header

- Item 1
- Item 2

\`\`\`python
def test():
    return "hello"
\`\`\`

Table test:

| Name | Value |
|------|-------|
| A    | 1     |
| B    | 2     |
`

export default function Home() {
  return (
    <div style={{ padding: 40, maxWidth: 800, margin: '0 auto' }}>
      <h1>Markdown Test</h1>
      <div>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {sampleMarkdown}
        </ReactMarkdown>
      </div>
      <hr />
      <h2>Without Plugins</h2>
      <div>
        <ReactMarkdown>
          {sampleMarkdown}
        </ReactMarkdown>
      </div>
      <hr />
      <h2>Raw Text Preview</h2>
      <pre style={{ background: '#f5f5f5', padding: 20, overflow: 'auto' }}>
        {sampleMarkdown}
      </pre>
    </div>
  )
}
