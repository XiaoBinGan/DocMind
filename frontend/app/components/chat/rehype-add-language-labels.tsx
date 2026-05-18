import { type Elements, type Transformer } from "unified"

/**
 * rehype 插件：为 <pre> 代码块添加语言标签栏。
 * 检测 <code> 的 class（如 "language-javascript" 或 "hljs javascript"），
 * 在 <pre> 内插入一个语言标签行。
 */
export function rehypeAddLanguageLabels() {
  return (tree: any) => {
    const nodes: any[] = []
    const walk = (node: any) => {
      if (!node || typeof node !== "object") return
      if (node.tagName === "pre") {
        // 找到子元素中的 code
        let lang = ""
        let codeEl: any = null
        if (Array.isArray(node.children)) {
          for (const child of node.children) {
            if (child && child.tagName === "code") {
              codeEl = child
              const classStr = child.properties?.className || child.props?.className || ""
              const classes = Array.isArray(classStr) ? classStr : String(classStr).split(/\s+/)
              lang = classes
                .find(c => c.startsWith("language-") || c === "hljs")
                ?.replace(/^language-/, "")
                .replace(/^hljs$/, "") || ""
              if (!lang) {
                // rehype-highlight 可能用 data-language
                lang = child.properties?.dataLanguage || child.props?.dataLanguage || ""
              }
              if (!lang) {
                // 尝试 properties.language
                lang = child.properties?.language || child.props?.language || ""
              }
              break
            }
          }
        }
        // 如果没有找到 code 子元素，尝试找嵌套 pre
        if (!codeEl && Array.isArray(node.children)) {
          for (const child of node.children) {
            if (child && child.tagName === "pre" && Array.isArray(child.children)) {
              for (const sub of child.children) {
                if (sub && sub.tagName === "code") {
                  codeEl = sub
                  const classStr = sub.properties?.className || ""
                  const classes = Array.isArray(classStr) ? classStr : String(classStr).split(/\s+/)
                  lang = classes
                    .find(c => c.startsWith("language-"))
                    ?.replace(/^language-/, "") || ""
                  if (!lang) {
                    lang = sub.properties?.dataLanguage || sub.props?.dataLanguage || ""
                  }
                  break
                }
              }
            }
          }
        }
        if (lang) {
          // 移除 lang- 前缀的 class（避免重复）
          if (codeEl?.properties?.className) {
            const cls = Array.isArray(codeEl.properties.className)
              ? codeEl.properties.className
              : String(codeEl.properties.className).split(/\s+/)
            codeEl.properties.className = cls.filter(c => !c.startsWith("language-"))
          }
          const labelNode = {
            type: "element",
            tagName: "div",
            properties: {
              className: "language-label",
            },
            children: [
              {
                type: "text",
                value: lang.toUpperCase(),
              },
            ],
          }
          if (node.children) {
            node.children.unshift(labelNode)
          } else {
            node.children = [labelNode]
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
