"use client"

import { useEffect, useRef, useState, useCallback } from "react"

interface MermaidBlockProps {
  code: string
  theme?: "dark" | "light"
}

// Counter for unique IDs
let mermaidCounter = 0

/**
 * Client component that renders Mermaid diagrams.
 * Uses dynamic import to avoid SSR/ESM issues with Next.js.
 */
export default function MermaidBlock({ code, theme = "dark" }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const idRef = useRef(`mermaid-${++mermaidCounter}`)

  const renderDiagram = useCallback(async () => {
    if (!containerRef.current || !code.trim()) {
      setLoading(false)
      return
    }

    try {
      // Dynamic import to avoid SSR issues
      const mermaid = (await import("mermaid")).default

      // Initialize mermaid with a unique id prefix
      mermaid.initialize({
        startOnLoad: false,
        theme: theme === "dark" ? "dark" : "default",
        securityLevel: "loose",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        themeVariables: theme === "dark"
          ? {
              darkMode: true,
              background: "#0a1628",
              primaryColor: "#00c9ff",
              primaryTextColor: "#e8f4ff",
              primaryBorderColor: "#1a3050",
              lineColor: "#6b8cae",
              secondaryColor: "#152238",
              tertiaryColor: "#0f1e35",
              textColor: "#e8f4ff",
              nodeTextColor: "#e8f4ff",
              edgeLabelBackground: "#0a1628",
            }
          : undefined,
      })

      const { svg } = await mermaid.render(idRef.current, code.trim())
      if (containerRef.current) {
        containerRef.current.innerHTML = svg
      }
      setLoading(false)
    } catch (err: any) {
      console.error("Mermaid render error:", err)
      setError(err?.message || "Failed to render Mermaid diagram")
      setLoading(false)
    }
  }, [code, theme])

  useEffect(() => {
    renderDiagram()
  }, [renderDiagram])

  if (error) {
    return (
      <div style={{
        padding: "1em",
        background: "rgba(239, 68, 68, 0.1)",
        border: "1px solid rgba(239, 68, 68, 0.3)",
        borderRadius: "8px",
        color: "#fca5a5",
        fontSize: "0.85em",
      }}>
        <div style={{ fontWeight: 600, marginBottom: "0.4em" }}>⚠️ Mermaid 渲染失败</div>
        <pre style={{ margin: 0, fontSize: "0.85em", opacity: 0.8, whiteSpace: "pre-wrap" }}>
          {code.trim()}
        </pre>
      </div>
    )
  }

  return (
    <div style={{
      position: "relative",
      minHeight: "40px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      {loading && (
        <div style={{
          color: "var(--text-secondary)",
          fontSize: "0.85em",
          padding: "0.5em",
        }}>
          加载图表中...
        </div>
      )}
      <div
        ref={containerRef}
        style={{
          display: loading ? "none" : "block",
          overflowX: "auto",
          textAlign: "center",
          width: "100%",
        }}
      />
    </div>
  )
}
