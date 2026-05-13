"use client"

import { useState, useEffect, useCallback } from "react"
import { api, Memory, MemoryStats } from "@/lib/api"
import Nav from "@/components/nav"
import {
  Plus, Trash2, Archive, Search, Tag, Brain,
  Star, BookOpen, Lightbulb, Heart, Filter,
  Sparkles, MessageSquare, Zap, ChevronDown, ChevronUp
} from "lucide-react"
import styles from "./page.module.css"

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  daily: <BookOpen size={14} />,
  long_term: <Brain size={14} />,
  preference: <Heart size={14} />,
  decision: <Lightbulb size={14} />,
  lesson: <Star size={14} />,
}

const CATEGORY_LABELS: Record<string, string> = {
  daily: "日常",
  long_term: "长期记忆",
  preference: "偏好",
  decision: "决策",
  lesson: "经验",
}

const CATEGORY_COLORS: Record<string, string> = {
  daily: "#00C9FF",
  long_term: "#7B61FF",
  preference: "#FF6B9D",
  decision: "#FFD740",
  lesson: "#00E676",
}

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([])
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [filterCat, setFilterCat] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [formContent, setFormContent] = useState("")
  const [formCategory, setFormCategory] = useState("daily")
  const [formTags, setFormTags] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [showTips, setShowTips] = useState(true)

  const loadMemories = useCallback(async () => {
    try {
      const [memRes, statRes] = await Promise.all([
        api.listMemories({
          category: filterCat || undefined,
          search: search || undefined,
          is_archived: showArchived ? 1 : 0,
        }),
        api.getMemoryStats(),
      ])
      setMemories(memRes.memories)
      setStats(statRes)
    } catch (e) {
      console.error("Failed to load memories:", e)
    } finally {
      setLoading(false)
    }
  }, [filterCat, search, showArchived])

  useEffect(() => { loadMemories() }, [loadMemories])

  const handleCreate = async () => {
    if (!formContent.trim()) return
    setSubmitting(true)
    try {
      const tags = formTags.trim() ? formTags.split(",").map(t => t.trim()).filter(Boolean) : undefined
      await api.createMemory({
        content: formContent.trim(),
        category: formCategory,
        tags,
      })
      setFormContent("")
      setFormTags("")
      setShowForm(false)
      loadMemories()
    } catch (e) {
      console.error("Failed to create memory:", e)
    } finally {
      setSubmitting(false)
    }
  }

  const handleArchive = async (mem: Memory) => {
    try {
      await api.updateMemory(mem.id, { is_archived: mem.is_archived ? 0 : 1 })
      loadMemories()
    } catch (e) { console.error(e) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这条记忆？")) return
    try {
      await api.deleteMemory(id)
      loadMemories()
    } catch (e) { console.error(e) }
  }

  const formatDate = (d: string) => {
    const dt = new Date(d)
    return dt.toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) + " " +
           dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
  }

  return (
    <div className={styles.container}>
      <Nav />
      <div className={styles.content}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>🧠 记忆管理</h1>
            {stats && (
              <p className={styles.subtitle}>
                共 {stats.total} 条记忆，{stats.active} 条活跃
              </p>
            )}
          </div>
          <button className={styles.addBtn} onClick={() => setShowForm(!showForm)}>
            <Plus size={16} /> 新增记忆
          </button>
        </div>

        <div className={styles.tipsSection}>
          <div
            className={styles.tipsHeader}
            onClick={() => setShowTips(!showTips)}
          >
            <div className={styles.tipsHeaderLeft}>
              <Sparkles size={16} />
              <span>记忆使用指南</span>
            </div>
            {showTips ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
          {showTips && (
            <div className={styles.tipsContent}>
              <div className={styles.tipsGrid}>
                <div className={styles.tipCard}>
                  <div className={styles.tipIcon}><Brain size={20} /></div>
                  <h3>什么是记忆？</h3>
                  <p>记忆是 AI 对话的持久化知识库。记录重要信息后，AI 在后续对话中会自动检索相关记忆，实现个性化回答。</p>
                </div>
                <div className={styles.tipCard}>
                  <div className={styles.tipIcon}><Zap size={20} /></div>
                  <h3>记录什么？</h3>
                  <p>用户偏好、重要决策、项目背景、关键结论、常用术语——任何 AI 再次对话时需要知道的上下文。</p>
                </div>
                <div className={styles.tipCard}>
                  <div className={styles.tipIcon}><MessageSquare size={20} /></div>
                  <h3>对话即记录</h3>
                  <p>聊天时对 AI 说"记住这个"，系统会自动提取关键信息并存入记忆库，无需手动创建。</p>
                </div>
                <div className={styles.tipCard}>
                  <div className={styles.tipIcon}><Filter size={20} /></div>
                  <h3>分类与标签</h3>
                  <p>5 大分类自动归档：日常、长期记忆、偏好、决策、经验。加上自定义标签，快速检索不迷路。</p>
                </div>
              </div>
              <div className={styles.tipsActions}>
                <div className={styles.tipAction}>
                  <span className={styles.tipActionEmoji}>💡</span>
                  <span>试试对 AI 说：<strong>"记住我喜欢简洁的技术文档"</strong></span>
                </div>
                <div className={styles.tipAction}>
                  <span className={styles.tipActionEmoji}>🏷️</span>
                  <span>标签可以按主题组织记忆，例如：<strong>项目名、人名、技术栈</strong></span>
                </div>
                <div className={styles.tipAction}>
                  <span className={styles.tipActionEmoji}>📦</span>
                  <span>不再需要的记忆可以<strong>归档</strong>而非删除，随时可以恢复</span>
                </div>
                <div className={styles.tipAction}>
                  <span className={styles.tipActionEmoji}>🔍</span>
                  <span>搜索支持全文匹配，输入关键词即可找到相关记忆</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {showForm && (
          <div className={styles.form}>
            <textarea
              className={styles.formInput}
              value={formContent}
              onChange={e => setFormContent(e.target.value)}
              placeholder="记录点什么..."
              rows={3}
            />
            <div className={styles.formRow}>
              <select
                className={styles.formSelect}
                value={formCategory}
                onChange={e => setFormCategory(e.target.value)}
              >
                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <input
                className={styles.formTags}
                value={formTags}
                onChange={e => setFormTags(e.target.value)}
                placeholder="标签（逗号分隔）"
              />
              <button
                className={styles.formSubmit}
                onClick={handleCreate}
                disabled={!formContent.trim() || submitting}
              >
                {submitting ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        )}

        {stats && stats.total > 0 && (
          <div className={styles.stats}>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
              stats.by_category[k] ? (
                <div
                  key={k}
                  className={`${styles.statCard} ${filterCat === k ? styles.statCardActive : ""}`}
                  style={{ borderLeftColor: CATEGORY_COLORS[k] }}
                  onClick={() => setFilterCat(filterCat === k ? null : k)}
                >
                  {CATEGORY_ICONS[k]}
                  <span className={styles.statLabel}>{v}</span>
                  <span className={styles.statCount}>{stats.by_category[k]}</span>
                </div>
              ) : null
            ))}
            {stats.archived > 0 && (
              <div
                className={`${styles.statCard} ${showArchived ? styles.statCardActive : ""}`}
                style={{ borderLeftColor: "var(--text-muted)" }}
                onClick={() => setShowArchived(!showArchived)}
              >
                <Archive size={14} />
                <span className={styles.statLabel}>已归档</span>
                <span className={styles.statCount}>{stats.archived}</span>
              </div>
            )}
          </div>
        )}

        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <Search size={14} className={styles.searchIcon} />
            <input
              className={styles.searchInput}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索记忆..."
            />
          </div>
          {(filterCat || search) && (
            <button className={styles.clearBtn} onClick={() => { setFilterCat(null); setSearch("") }}>
              清除筛选
            </button>
          )}
        </div>

        {loading ? (
          <div className={styles.loading}>加载中...</div>
        ) : memories.length === 0 ? (
          <div className={styles.empty}>
            <Brain size={48} className={styles.emptyIcon} />
            <p className={styles.emptyTitle}>还没有记忆</p>
            <p className={styles.emptyDesc}>记录偏好、决策和重要信息，AI 对话时会自动引用</p>
            <button className={styles.emptyBtn} onClick={() => { setShowForm(true); setShowTips(false) }}>
              <Plus size={14} /> 创建第一条记忆
            </button>
          </div>
        ) : (
          <div className={styles.list}>
            {memories.map(mem => (
              <div key={mem.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <span
                    className={styles.cardCat}
                    style={{ color: CATEGORY_COLORS[mem.category] || "var(--text-secondary)" }}
                  >
                    {CATEGORY_ICONS[mem.category] || <Tag size={14} />}
                    {CATEGORY_LABELS[mem.category] || mem.category}
                  </span>
                  <span className={styles.cardDate}>{formatDate(mem.updated_at)}</span>
                </div>
                <p className={styles.cardContent}>{mem.content}</p>
                {mem.tags && mem.tags.length > 0 && (
                  <div className={styles.cardTags}>
                    {mem.tags.map((t, i) => (
                      <span key={i} className={styles.tag}>{t}</span>
                    ))}
                  </div>
                )}
                <div className={styles.cardActions}>
                  <button className={styles.cardAction} onClick={() => handleArchive(mem)} title={mem.is_archived ? "取消归档" : "归档"}>
                    <Archive size={13} />
                  </button>
                  <button className={styles.cardAction} onClick={() => handleDelete(mem.id)} title="删除">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
