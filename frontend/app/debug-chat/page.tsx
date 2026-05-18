"use client"

import { useState } from "react"

export default function DebugChat() {
  const [response, setResponse] = useState("")
  const [loading, setLoading] = useState(false)

  const test = async () => {
    setLoading(true)
    setResponse("")
    
    try {
      const res = await fetch("http://localhost:8000/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Write a python example with a markdown table",
          stream: true
        })
      })
      
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      
      while (true) {
        const { done, value } = await reader!.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""
        
        for (const line of lines) {
          if (line.startsWith("event:")) continue
          if (line.startsWith("data:")) {
            const data = line.slice(5).trim()
            if (data && data !== "\\n") {
              setResponse(prev => prev + data)
            }
          }
        }
      }
    } catch (e) {
      setResponse("Error: " + e)
    }
    setLoading(false)
  }

  return (
    <div style={{ padding: 40 }}>
      <h1>Chat API 诊断</h1>
      <button onClick={test} disabled={loading}>
        {loading ? "请求中..." : "发送测试请求"}
      </button>
      
      <h2>原始响应文本：</h2>
      <pre style={{ background: "#111", color: "#0f0", padding: 20, whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 300, overflow: "auto" }}>
        {response || "(空)"}
      </pre>
      
      <h2>检查是否有换行符：</h2>
      <pre style={{ background: "#222", color: "#ff0", padding: 20 }}>
        {response ? `字符数: ${response.length}\n换行数: ${(response.match(/\n/g) || []).length}\n是否包含 # : ${(response.includes("#") ? "是" : "否")}\n是否包含 \` : ${(response.includes("\`") ? "是" : "否")}\n是否包含 | : ${(response.includes("|") ? "是" : "否")}\n是否包含 - : ${(response.includes("-") ? "是" : "否")}` : "无响应"}
      </pre>
      
      <h2>渲染结果：</h2>
      <div style={{ background: "#0f1e35", padding: 20, borderRadius: 8 }}>
        {response ? decodeMarkdown(response) : "(渲染需要 react-markdown，这里只展示原始文本)"}
      </div>
    </div>
  )
}

function decodeMarkdown(md: string): string {
  // 简单显示，不做完整解析
  return md.split("\n").map((line, i) => {
    if (line.startsWith("#")) return <h2 key={i} style={{ color: "#00c9ff" }}>{line.replace(/^#+\s*/, "")}</h2>
    if (line.startsWith("- ")) return <div key={i} style={{ paddingLeft: 20 }}>• {line.slice(2)}</div>
    if (line.startsWith("|")) return <div key={i} style={{ fontFamily: "monospace" }}>{line}</div>
    return <div key={i}>{line}</div>
  })
}
