/**
 * rehype 插件：将 mermaid 代码块转换为 data-mermaid 属性的 div 元素。
 *
 * 在 react-markdown 的 components prop 中，
 * 对 pre > code[data-mermaid] 进行自定义渲染为 MermaidBlock 组件。
 *
 * 这个插件在 AST 层面工作，将：
 *   <pre><code class="language-mermaid">...</code></pre>
 * 转换为：
 *   <pre data-mermaid><code data-mermaid>...</code></pre>
 *
 * 这样在 components 配置中可以通过 code props 检测到 mermaid 代码块。
 */
export function rehypeMermaidBlock() {
  return (tree: any) => {
    const walk = (node: any) => {
      if (!node || typeof node !== "object") return

      if (node.tagName === "pre" && Array.isArray(node.children)) {
        for (const child of node.children) {
          if (child && child.tagName === "code") {
            const classStr = child.properties?.className || ""
            const classes = Array.isArray(classStr) ? classStr : String(classStr).split(/\s+/)
            const isMermaid = classes.some((c: string) => c === "language-mermaid")

            if (isMermaid) {
              // Mark both pre and code with data-mermaid attribute
              node.properties = node.properties || {}
              node.properties["dataMermaid"] = true
              child.properties = child.properties || {}
              child.properties["dataMermaid"] = true
            }
          }
        }
      }

      if (Array.isArray(node.children)) {
        node.children.forEach(walk)
      }
    }
    walk(tree)
  }
}
