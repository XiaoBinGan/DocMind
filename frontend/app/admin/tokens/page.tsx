"use client"

import { useEffect, useState } from "react"
import { api, type UserTokenSummary } from "@/lib/api"
import Nav from "@/components/nav"
import styles from "./page.module.css"

export default function AdminTokenPage() {
  const [summaries, setSummaries] = useState<UserTokenSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [selectedUserId, setSelectedUserId] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    loadSummaries()
  }, [days, selectedUserId])

  async function loadSummaries() {
    setLoading(true)
    setError("")
    try {
      const data = await api.getAdminTokenSummary(selectedUserId || undefined, days)
      setSummaries(data)
    } catch (e: any) {
      setError(e.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (n: number) => n.toLocaleString()
  const grandTotal = summaries.reduce((s, u) => s + u.total_tokens, 0)

  const sorted = [...summaries].sort((a, b) => b.total_tokens - a.total_tokens)

  return (
    <div style={{ minHeight: "100vh", background: "#020617" }}>
      <Nav />
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>Token 使用总览</h1>
          <div className={styles.controls}>
            <div className={styles.daysSelector}>
              <label>最近：</label>
              {[7, 30, 90, 365].map(d => (
                <button
                  key={d}
                  className={`${styles.dayBtn} ${days === d ? styles.dayBtnActive : ""}`}
                  onClick={() => setDays(d)}
                >
                  {d}天
                </button>
              ))}
            </div>
            <div className={styles.filterSection}>
              <label>按用户筛选：</label>
              <input
                type="text"
                placeholder="输入用户名..."
                className={styles.filterInput}
                value={selectedUserId}
                onChange={e => setSelectedUserId(e.target.value)}
              />
            </div>
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        {loading && !summaries.length ? (
          <div className={styles.loading}>加载中...</div>
        ) : (
          <>
            <div className={styles.summaryRow}>
              <div className={styles.summaryItem}>
                <div className={styles.summaryValue}>{formatNumber(grandTotal)}</div>
                <div className={styles.summaryLabel}>总 Token</div>
              </div>
              <div className={styles.summaryItem}>
                <div className={styles.summaryValue}>{formatNumber(summaries.reduce((s, u) => s + u.turn_count, 0))}</div>
                <div className={styles.summaryLabel}>总轮次</div>
              </div>
              <div className={styles.summaryItem}>
                <div className={styles.summaryValue}>{summaries.length}</div>
                <div className={styles.summaryLabel}>活跃用户</div>
              </div>
            </div>

            <div className={styles.tableSection}>
              <h3 className={styles.sectionTitle}>用户用量排行</h3>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>显示名</th>
                      <th>输入 Token</th>
                      <th>输出 Token</th>
                      <th>总计</th>
                      <th>轮次</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.length > 0 ? (
                      sorted.map((u, idx) => (
                        <tr key={u.user_id}>
                          <td className={styles.nameCell}>{u.username}</td>
                          <td>{u.display_name || "—"}</td>
                          <td>{formatNumber(u.prompt_tokens)}</td>
                          <td>{formatNumber(u.completion_tokens)}</td>
                          <td className={styles.totalCell}>{formatNumber(u.total_tokens)}</td>
                          <td>{formatNumber(u.turn_count)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={6} className={styles.noData}>暂无数据</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {sorted.length > 0 && (
              <div className={styles.rankingChart}>
                <h3 className={styles.sectionTitle}>用量分布</h3>
                <div className={styles.horizontalBars}>
                  {sorted.slice(0, 20).map((u) => {
                    const pct = grandTotal > 0 ? (u.total_tokens / grandTotal) * 100 : 0
                    return (
                      <div key={u.user_id} className={styles.hBarItem}>
                        <div className={styles.hBarLabel}>{u.username}</div>
                        <div className={styles.hBarContainer}>
                          <div
                            className={styles.hBar}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <div className={styles.hBarValue}>{formatNumber(u.total_tokens)}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
