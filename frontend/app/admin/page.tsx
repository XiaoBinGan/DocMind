"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@/lib/auth"
import { api, type AdminUser, type AdminConversation, type AdminConversationDetail, type UserTokenSummary } from "@/lib/api"
import Nav from "@/components/nav"

type Tab = "users" | "conversations"
type DetailMode = "list" | "detail"

/* ─── User Table ─── */

function UserTable({ users, onUpdate, onToggleTab, tokenMap }: {
  users: AdminUser[]
  onUpdate: (id: string, action: string) => void
  onToggleTab: (t: Tab) => void
  tokenMap: Record<string, UserTokenSummary>
}) {
  const renderTokenUsage = (userId: string) => {
    const tokenInfo = tokenMap[userId]
    if (!tokenInfo || tokenInfo.total_tokens === 0) return <span style={{ color: "#475569" }}>—</span>
    const { total_tokens, turn_count, prompt_tokens, completion_tokens } = tokenInfo
    const label = total_tokens > 999 ? `${(total_tokens / 1000).toFixed(1)}K` : `${total_tokens}`
    const color = total_tokens > 100000 ? "#ef4444" : total_tokens > 10000 ? "#f59e0b" : "#22c55e"
    const title = `输入: ${prompt_tokens.toLocaleString()} | 输出: ${completion_tokens.toLocaleString()}`
    return (
      <span style={{ color, fontFamily: "'JetBrains Mono', 'SF Mono', monospace", fontWeight: 500, whiteSpace: "nowrap" }} title={title}>
        {label} ({turn_count}轮)
      </span>
    )
  }

  return (
    <div>
      <h2 style={{ fontSize: "1.2rem", fontWeight: 600, marginBottom: 16, color: "#e2e8f0" }}>
        用户列表 ({users.length} 人)
      </h2>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #334155" }}>
            {["用户名", "昵称", "邮箱", "状态", "角色", "对话数", "Token 用量", "注册时间", "操作"].map(h => (
              <th key={h} style={{ padding: "12px 10px", textAlign: "left", color: "#94a3b8", fontWeight: 500, fontSize: "0.8rem", textTransform: "uppercase" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id} style={{ borderBottom: "1px solid #1e293b" }}>
              <td style={{ padding: "10px", color: "#f1f5f9", fontWeight: 500 }}>{u.username}</td>
              <td style={{ padding: "10px", color: "#cbd5e1" }}>{u.display_name || "-"}</td>
              <td style={{ padding: "10px", color: "#cbd5e1" }}>{u.email || "-"}</td>
              <td style={{ padding: "10px" }}>
                <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 99, fontSize: "0.75rem", background: u.is_active ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", color: u.is_active ? "#22c55e" : "#ef4444" }}>{u.is_active ? "正常" : "禁用"}</span>
              </td>
              <td style={{ padding: "10px" }}>
                <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 99, fontSize: "0.75rem", background: u.is_admin ? "rgba(168,85,247,0.15)" : "rgba(100,116,139,0.15)", color: u.is_admin ? "#a855f7" : "#64748b" }}>{u.is_admin ? "管理员" : "普通用户"}</span>
              </td>
              <td style={{ padding: "10px", color: "#94a3b8" }}>{u.conversation_count}</td>
              <td style={{ padding: "10px" }}>{renderTokenUsage(u.id)}</td>
              <td style={{ padding: "10px", color: "#64748b", fontSize: "0.8rem" }}>{u.created_at.split("T")[0]}</td>
              <td style={{ padding: "10px" }}>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {u.is_active ? (
                    <button onClick={() => onUpdate(u.id, "deactivate")} style={btnStyle({ color: "#ef4444" })}>禁用</button>
                  ) : (
                    <button onClick={() => onUpdate(u.id, "activate")} style={btnStyle({ color: "#22c55e" })}>启用</button>
                  )}
                  {u.is_admin ? (
                    <button onClick={() => onUpdate(u.id, "revoke_admin")} style={btnStyle({ color: "#a855f7" })}>撤销管理</button>
                  ) : (
                    <button onClick={() => onUpdate(u.id, "grant_admin")} style={btnStyle({ color: "#a855f7" })}>授予管理</button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function btnStyle({ color = "#94a3b8" }: { color?: string }) {
  return {
    padding: "4px 10px",
    fontSize: "0.75rem",
    border: "none",
    borderRadius: 6,
    background: `${color}18`,
    color,
    cursor: "pointer",
    whiteSpace: "nowrap",
  }
}

/* ─── Conversation List ─── */

function ConversationList({ convs, onSelect, onBack, userFilter }: {
  convs: AdminConversation[]
  onSelect: (id: string) => void
  onBack: () => void
  userFilter: AdminUser | null
}) {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const total = convs.length

  const filtered = convs.filter(c =>
    !search || c.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <button onClick={onBack} style={{
        background: "none",
        border: "none",
        color: "#94a3b8",
        cursor: "pointer",
        fontSize: "0.85rem",
        marginBottom: 16,
        padding: "4px 0",
      }}>← 返回</button>

      {userFilter && (
        <div style={{
          padding: "10px 16px",
          background: "rgba(168,85,247,0.08)",
          border: "1px solid rgba(168,85,247,0.2)",
          borderRadius: 8,
          marginBottom: 16,
          fontSize: "0.85rem",
          color: "#a855f7",
        }}>
          查看用户 <strong>{userFilter.username}</strong> 的对话 ({total} 条)
        </div>
      )}

      <input
        type="text"
        placeholder="搜索对话标题..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{
          width: "100%",
          padding: "10px 14px",
          background: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 8,
          color: "#e2e8f0",
          fontSize: "0.875rem",
          marginBottom: 16,
          outline: "none",
        }}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {filtered.map(c => (
          <div key={c.id} onClick={() => onSelect(c.id)} style={{
            padding: "12px 16px",
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 8,
            cursor: "pointer",
            transition: "border-color 0.2s",
          }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = "#3b82f6")}
            onMouseLeave={e => (e.currentTarget.style.borderColor = "#1e293b")}
          >
            <div style={{ color: "#e2e8f0", fontWeight: 500, marginBottom: 4, fontSize: "0.9rem" }}>
              {c.title}
            </div>
            <div style={{ display: "flex", gap: 16, fontSize: "0.75rem", color: "#64748b" }}>
              <span>用户: {c.user_id ? c.user_id.slice(0, 8) + '...' : '(无用户)'}</span>
              <span>类型: {c.chat_type === "general" ? "通用" : "知识库"}</span>
              <span>消息: {c.message_count} 条</span>
              <span>{c.updated_at.split("T")[0]}</span>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: "#475569" }}>
            {search ? "无匹配结果" : "暂无对话"}
          </div>
        )}
      </div>
    </div>
  )
}

/* ─── Conversation Detail ─── */

function ConversationDetail({ detail, onBack }: {
  detail: AdminConversationDetail
  onBack: () => void
}) {
  return (
    <div>
      <button onClick={onBack} style={{
        background: "none",
        border: "none",
        color: "#94a3b8",
        cursor: "pointer",
        fontSize: "0.85rem",
        marginBottom: 16,
        padding: "4px 0",
      }}>← 返回列表</button>

      <div style={{
        padding: "12px 16px",
        background: "rgba(59,130,246,0.08)",
        border: "1px solid rgba(59,130,246,0.2)",
        borderRadius: 8,
        marginBottom: 20,
        fontSize: "0.85rem",
        color: "#93c5fd",
        display: "flex",
        gap: 24,
        flexWrap: "wrap",
      }}>
        <span><strong>用户:</strong> {detail.user_id ? detail.user_id.slice(0, 8) + '...' : '(无用户)'}</span>
        <span><strong>类型:</strong> {detail.chat_type === "general" ? "通用" : "知识库"}</span>
        <span><strong>消息:</strong> {detail.messages.length} 条</span>
        <span><strong>时间:</strong> {detail.created_at.split("T")[0]}</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {detail.messages.map(m => (
          <div key={m.id} style={{
            display: "flex",
            justifyContent: m.role === "user" ? "flex-end" : "flex-start",
          }}>
            <div style={{
              maxWidth: "75%",
              padding: "10px 14px",
              borderRadius: 12,
              background: m.role === "user" ? "#2563eb" : "#1e293b",
              color: m.role === "user" ? "#fff" : "#e2e8f0",
              fontSize: "0.875rem",
              lineHeight: 1.6,
              wordBreak: "break-word",
            }}>
              <div style={{ fontSize: "0.7rem", marginBottom: 4, opacity: 0.6 }}>
                {m.role === "user" ? "用户" : "AI"} · {m.created_at.split("T")[1]?.slice(0, 5)}
              </div>
              <pre style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontFamily: "inherit",
              }}>{m.content}</pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Main Admin Page ─── */

export default function AdminPage() {
  const { user, loading } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>("users")
  const [users, setUsers] = useState<AdminUser[]>([])
  const [convs, setConvs] = useState<AdminConversation[]>([])
  const [detail, setDetail] = useState<AdminConversationDetail | null>(null)
  const [detailMode, setDetailMode] = useState<DetailMode>("list")
  const [userFilter, setUserFilter] = useState<AdminUser | null>(null)
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [loadingConvs, setLoadingConvs] = useState(false)
  const [toast, setToast] = useState<string>("")
  const [tokenMap, setTokenMap] = useState<Record<string, UserTokenSummary>>({})

  const loadTokenMap = useCallback(async () => {
    const map: Record<string, UserTokenSummary> = {}
    try {
      const allSummary = await api.getAdminTokenSummary(undefined, 365)
      for (const s of allSummary) {
        map[s.user_id] = s
      }
      setTokenMap(map)
    } catch {
      // 静默失败
    }
  }, [])

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true)
    try {
      const data = await api.getAdminUsers()
      setUsers(data)
      await loadTokenMap()
    } catch (e: any) {
      setToast(e.message || "加载用户失败")
      setTimeout(() => setToast(""), 3000)
    } finally {
      setLoadingUsers(false)
    }
  }, [])

  const loadConvs = useCallback(async (userId?: string) => {
    setLoadingConvs(true)
    try {
      const data = await api.getAdminConversations(userId)
      setConvs(data.conversations)
    } catch (e: any) {
      setToast(e.message || "加载对话失败")
      setTimeout(() => setToast(""), 3000)
    } finally {
      setLoadingConvs(false)
    }
  }, [])

  useEffect(() => { if (activeTab === "users") loadUsers() }, [activeTab, loadUsers])
  useEffect(() => { if (activeTab === "conversations" && detailMode === "list") loadConvs() }, [activeTab, detailMode, loadConvs])

  const handleUpdateUser = async (id: string, action: string) => {
    try {
      await api.updateAdminUser(id, action)
      await loadUsers()
      if (userFilter?.id === id) await loadConvs(id)
    } catch (e: any) {
      setToast(e.message || "操作失败")
      setTimeout(() => setToast(""), 3000)
    }
  }

  const handleSelectConv = async (id: string) => {
    const data = await api.getAdminConversationDetail(id)
    setDetail(data)
    setDetailMode("detail")
  }

  // 权限检查 — 在 hooks 之后
  if (loading) return <div style={{ color: "#94a3b8", padding: 40 }}>加载中...</div>
  if (!user?.is_admin) {
    return (
      <div style={{ minHeight: "100vh", background: "#020617" }}>
        <Nav />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>🔒</div>
            <h2 style={{ color: "#e2e8f0" }}>无权访问</h2>
            <p style={{ color: "#64748b" }}>仅管理员可访问此页面</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: "100vh", background: "#020617" }}>
      <Nav />

      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 9999,
          padding: "10px 16px", background: "#1e293b", border: "1px solid #334155",
          borderRadius: 8, color: "#e2e8f0", fontSize: "0.85rem",
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
        }}>{toast}</div>
      )}

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 24px 80px" }}>
        <h1 style={{
          fontSize: "1.5rem", fontWeight: 700, color: "#e2e8f0",
          marginBottom: 8, fontFamily: "'Space Grotesk', sans-serif",
        }}>
          🛡️ 管理后台
        </h1>
        <p style={{ color: "#64748b", fontSize: "0.875rem", marginBottom: 24 }}>
          管理用户权限与查看对话记录
        </p>

        {/* Tabs */}
        <div style={{ display: "flex", gap: "4px", marginBottom: 24, borderBottom: "1px solid #1e293b" }}>
          {(["users", "conversations"] as Tab[]).map(t => (
            <button key={t} onClick={() => { setActiveTab(t); setDetailMode("list"); setUserFilter(null); }} style={{
              padding: "10px 20px",
              background: activeTab === t ? "#2563eb" : "transparent",
              border: "none",
              borderBottom: activeTab === t ? "2px solid #3b82f6" : "2px solid transparent",
              borderRadius: "8px 8px 0 0",
              color: activeTab === t ? "#fff" : "#64748b",
              cursor: "pointer",
              fontSize: "0.875rem",
              fontWeight: activeTab === t ? 600 : 400,
            }}>{t === "users" ? "用户管理" : "对话查看"}</button>
          ))}
        </div>

        {/* Content */}
        {activeTab === "users" && (
          detailMode === "list" && (
            loadingUsers ? (
              <div style={{ textAlign: "center", padding: 40, color: "#475569" }}>加载用户...</div>
            ) : (
              <UserTable users={users} onUpdate={handleUpdateUser} onToggleTab={setActiveTab} tokenMap={tokenMap} />
            )
          )
        )}

        {activeTab === "conversations" && detailMode === "list" && (
          <ConversationList
            convs={convs}
            onSelect={handleSelectConv}
            onBack={() => { setDetailMode("list") }}
            userFilter={userFilter}
          />
        )}

        {activeTab === "conversations" && detailMode === "detail" && detail && (
          <ConversationDetail detail={detail} onBack={() => setDetailMode("list")} />
        )}
      </div>
    </div>
  )
}
