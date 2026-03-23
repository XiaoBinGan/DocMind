"use client"

import { useState, useEffect } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { ChevronRight, ChevronDown, FileText, Layers, ArrowLeft, RefreshCw, Loader } from "lucide-react"
import { api, Document, IndexNode } from "@/lib/api"
import styles from "./page.module.css"

interface TreeNode extends IndexNode {
  expanded: boolean
  selected: boolean
}

export default function IndexTreePage() {
  const searchParams = useSearchParams()
  const docId = searchParams.get("id")

  const [document, setDocument] = useState<Document | null>(null)
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<IndexNode | null>(null)

  useEffect(() => {
    if (docId) {
      loadDocument()
    }
  }, [docId])

  const loadDocument = async () => {
    if (!docId) return
    setLoading(true)
    try {
      const doc = await api.getDocument(docId)
      setDocument(doc)
      if (doc.index_tree) {
        setTree(expandAll(doc.index_tree as IndexNode))
      }
    } catch (error) {
      console.error("Failed to load document:", error)
    } finally {
      setLoading(false)
    }
  }

  const expandAll = (node: IndexNode): TreeNode => {
    return {
      ...node,
      expanded: node.level < 2, // Auto-expand first 2 levels
      selected: false,
      children: node.children.map(expandAll)
    }
  }

  const toggleNode = (nodeId: string) => {
    if (!tree) return
    setTree(toggleNodeRecursive(tree, nodeId))
  }

  const toggleNodeRecursive = (node: TreeNode, nodeId: string): TreeNode => {
    if (node.id === nodeId) {
      return { ...node, expanded: !node.expanded }
    }
    return {
      ...node,
      children: node.children.map(child => toggleNodeRecursive(child, nodeId))
    }
  }

  const selectNode = (node: IndexNode) => {
    setSelectedNode(node)
    // Highlight selected path
    if (tree) {
      setTree(highlightPath(tree, node.id))
    }
  }

  const highlightPath = (node: TreeNode, targetId: string): TreeNode => {
    let isInPath = node.id === targetId
    const newChildren = node.children.map(child => {
      const result = highlightPath(child, targetId)
      if (result.selected) isInPath = true
      return result
    })
    return {
      ...node,
      selected: isInPath && node.id !== targetId,
      expanded: isInPath || node.expanded,
      children: newChildren
    }
  }

  const renderNode = (node: TreeNode, depth: number = 0) => {
    const hasChildren = node.children && node.children.length > 0
    const isSelected = selectedNode?.id === node.id

    return (
      <div key={node.id} className={styles.nodeContainer}>
        <div
          className={`${styles.node} ${isSelected ? styles.nodeSelected : ""}`}
          style={{ paddingLeft: `${depth * 24 + 12}px` }}
          onClick={() => selectNode(node)}
        >
          {hasChildren ? (
            <button
              className={styles.expandBtn}
              onClick={(e) => { e.stopPropagation(); toggleNode(node.id) }}
            >
              {node.expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
          ) : (
            <span className={styles.expandPlaceholder} />
          )}
          
          <span className={`${styles.levelIndicator} ${styles[`level${node.level}`]}`}>
            {node.level === 0 ? "根" : `L${node.level}`}
          </span>
          
          <span className={styles.nodeTitle}>{node.title}</span>
          
          <span className={styles.pageRange}>
            P{node.page_start}{node.page_end !== node.page_start ? `-${node.page_end}` : ""}
          </span>
        </div>

        {hasChildren && node.expanded && (
          <div className={styles.children}>
            {node.children.map(child => renderNode(child as TreeNode, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <Loader size={32} className={styles.spinner} />
          <p>加载索引树...</p>
        </div>
      </div>
    )
  }

  if (!document) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <FileText size={48} />
          <p>文档未找到</p>
          <Link href="/documents" className={styles.backLink}>
            返回文档列表
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      {/* Background Effects */}
      <div className={styles.bgGradient} />
      <div className={styles.bgGrid} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/documents" className={styles.backBtn}>
            <ArrowLeft size={20} />
            <span>返回</span>
          </Link>
          <div className={styles.titleGroup}>
            <Layers size={24} className={styles.titleIcon} />
            <div>
              <h1 className={styles.title}>索引树</h1>
              <p className={styles.subtitle}>{document.name}</p>
            </div>
          </div>
          <button className={styles.refreshBtn} onClick={loadDocument} title="刷新">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        {/* Tree View */}
        <div className={styles.treePanel}>
          <div className={styles.treeHeader}>
            <FileText size={16} />
            <span>文档结构</span>
            <span className={styles.nodeCount}>
              {tree ? countNodes(tree) : 0} 个节点
            </span>
          </div>
          
          <div className={styles.treeContainer}>
            {tree ? (
              renderNode(tree)
            ) : (
              <p className={styles.noTree}>暂无索引数据</p>
            )}
          </div>
        </div>

        {/* Detail Panel */}
        <div className={styles.detailPanel}>
          {selectedNode ? (
            <>
              <div className={styles.detailHeader}>
                <span className={`${styles.levelBadge} ${styles[`level${selectedNode.level}`]}`}>
                  {selectedNode.level === 0 ? "根节点" : `层级 ${selectedNode.level}`}
                </span>
                <span className={styles.detailPages}>
                  页面 {selectedNode.page_start} - {selectedNode.page_end}
                </span>
              </div>
              
              <h2 className={styles.detailTitle}>{selectedNode.title}</h2>
              
              {selectedNode.content_summary && (
                <div className={styles.detailSection}>
                  <h3>内容摘要</h3>
                  <p>{selectedNode.content_summary}</p>
                </div>
              )}
              
              <div className={styles.detailSection}>
                <h3>节点信息</h3>
                <div className={styles.detailInfo}>
                  <div className={styles.infoItem}>
                    <span className={styles.infoLabel}>节点 ID</span>
                    <span className={styles.infoValue}>{selectedNode.id}</span>
                  </div>
                  <div className={styles.infoItem}>
                    <span className={styles.infoLabel}>起始页</span>
                    <span className={styles.infoValue}>{selectedNode.page_start}</span>
                  </div>
                  <div className={styles.infoItem}>
                    <span className={styles.infoLabel}>结束页</span>
                    <span className={styles.infoValue}>{selectedNode.page_end}</span>
                  </div>
                  <div className={styles.infoItem}>
                    <span className={styles.infoLabel}>子节点数</span>
                    <span className={styles.infoValue}>{selectedNode.children?.length || 0}</span>
                  </div>
                </div>
              </div>

              <div className={styles.detailActions}>
                <Link 
                  href={`/chat?doc=${document.id}`}
                  className={styles.chatBtn}
                >
                  基于此节点对话
                </Link>
              </div>
            </>
          ) : (
            <div className={styles.noSelection}>
              <Layers size={48} />
              <p>选择左侧节点查看详情</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function countNodes(node: IndexNode): number {
  let count = 1
  if (node.children) {
    for (const child of node.children) {
      count += countNodes(child)
    }
  }
  return count
}
