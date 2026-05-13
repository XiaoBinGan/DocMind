"use client"

import { useState, useEffect, useCallback } from "react"
import { api, Memory, MemoryStats } from "@/lib/api"
import Nav from "@/components/nav"
import {
  Plus, Trash2, Archive, Search, Tag, Brain,
  Star, BookOpen, Lightbulb, Heart, Filter
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
            <p>{showArchived ? "没有归档的记忆" : "还没有记忆，点击上方按钮创建"}</p>
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
