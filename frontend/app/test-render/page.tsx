"use client"

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import styles from "./page.module.css"

// 测试 markdown 内容
const TEST_CASES = [
  {
    title: "代码块",
    content: `这是一个代码块示例：

\`\`\`python
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
\`\`\`

这是一个行内代码示例：\`const x = 10;\`
`
  },
  {
    title: "表格",
    content: `这是一个表格示例：

| 功能 | 状态 | 优先级 |
|------|------|--------|
| 代码高亮 | ✅ 完成 | P0 |
| 表格渲染 | ✅ 完成 | P0 |
| 数学公式 | ⏳ 待开发 | P1 |
| 图片上传 | ❌ 未实现 | P2 |
`
  },
  {
    title: "标题",
    content: `# 一级标题
## 二级标题
### 三级标题
#### 四级标题
`
  },
  {
    title: "列表",
    content: `## 无序列表
- 项目 A
- 项目 B
- 项目 C

## 有序列表
1. 第一步
2. 第二步
3. 第三步
`
  },
  {
    title: "加粗和斜体",
    content: `这是**加粗文本**和*斜体文本*。

这也是***加粗斜体***。
`
  },
  {
    title: "引用",
    content: `> 这是一个引用段落
> 可以有多行

> 另一段引用
`
  },
  {
    title: "混合内容（模拟真实 LLM 输出）",
    content: `# 道路养护技术综述

## 1. 定义与核心目标
**道路养护**是交通基础设施管理的核心环节，旨在保障通行安全与服务水平。

## 2. 主要作业分类

| 类别 | 典型场景 | 常用技术 |
|------|------|------|
| 日常养护 | 路面清扫、标线修复 | 机械化保洁 |
| 预防性养护 | 路面初衰期 | 微表处 |
| 修复性养护 | 结构性破坏 | 铣刨重铺 |

## 3. 关键技术

### 3.1 检测智能化
使用**探地雷达 (GPR)** 和 **AI 病害自动识别**。

### 3.2 决策数据化
基于 RTP/RQI/PQI 的路况评价模型。

## 4. 总结

> 道路养护应从"事后修复"转向"预防+精准干预"。

**关键指标**：PQI > 80 时进行预防性养护效果最佳。
`
  }
]

function TestCard({ test, index }: { test: typeof TEST_CASES[0]; index: number }) {
  const [showResult, setShowResult] = useState(false)
  
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h3 className={styles.title}>测试 {index + 1}: {test.title}</h3>
        <button 
          className={styles.toggleBtn}
          onClick={() => setShowResult(!showResult)}
        >
          {showResult ? "隐藏" : "显示"}
        </button>
      </div>
      
      {showResult && (
        <>
          <div className={styles.preview}>
            <h4>原始内容：</h4>
            <pre className={styles.raw}>{test.content}</pre>
          </div>
          
          <div className={styles.result}>
            <h4>渲染结果：</h4>
            <div className={styles.md}>
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]} 
                rehypePlugins={[rehypeHighlight]}
              >
                {test.content}
              </ReactMarkdown>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function TestRenderPage() {
  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>Markdown 渲染测试</h1>
      <p className={styles.description}>
        测试 DocMind 的 markdown 渲染效果。点击"显示"查看渲染结果。
      </p>
      
      <div className={styles.testList}>
        {TEST_CASES.map((test, index) => (
          <TestCard key={index} test={test} index={index} />
        ))}
      </div>
    </div>
  )
}
