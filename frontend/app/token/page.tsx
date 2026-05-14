"use client"

import { useEffect, useState } from "react"
import { api, type TokenSummary, type TokenDailyStat, type TokenUsageRecord } from "@/lib/api"
import Nav from "@/components/nav"
import styles from "./page.module.css"

export default function TokenPage() {
  const [summary, setSummary] = useState<TokenSummary | null>(null)
  const [usageRecords, setUsageRecords] = useState<TokenUsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [error, setError] = useState("")

  useEffect(() => {
    loadSummary()
    loadUsageRecords()
  }, [days])

  async function loadSummary() {
    setLoading(true)
    setError("")
    try {
      const data = await api.getTokenSummary(days)
      setSummary(data)
    } catch (e: any) {
      setError(e.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  async function loadUsageRecords() {
    try {
      const records = await api.getTokenUsage(days)
      setUsageRecords(records)
    } catch (e: any) {
      console.error("Failed to load usage records:", e)
    }
  }

  const formatNumber = (n: number) => n.toLocaleString()

  const maxDaily = Math.max(...(summary?.daily.map((d: TokenDailyStat) => d.tokens) || [1]))

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      <Nav />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 24px 80px" }}>
        <div className={styles.header}>
          <h1 className={styles.title}>Token 使用情况</h1>
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
        </div>

        {error && <div className={styles.error}>{error}</div>}

        {loading && !summary ? (
          <div className={styles.loading}>加载中...</div>
        ) : summary ? (
          <>
            <div className={styles.cards}>
              <div className={styles.card}>
                <span className={styles.cardLabel}>输入 Token</span>
                <span className={styles.cardValue}>{formatNumber(summary.total_prompt)}</span>
              </div>
              <div className={styles.card}>
                <span className={styles.cardLabel}>输出 Token</span>
                <span className={styles.cardValue}>{formatNumber(summary.total_completion)}</span>
              </div>
              <div className={styles.card}>
                <span className={styles.cardLabel}>总计 Token</span>
                <span className={styles.cardValue}>{formatNumber(summary.total_all)}</span>
              </div>
              <div className={styles.card}>
                <span className={styles.cardLabel}>对话轮次</span>
                <span className={styles.cardValue}>{formatNumber(summary.turn_count)}</span>
              </div>
            </div>

            {summary.daily.length > 0 && (
              <div className={styles.chartSection}>
                <h3 className={styles.sectionTitle}>每日用量</h3>
                <div className={styles.barChart}>
                  {summary.daily.map((day: TokenDailyStat) => (
                    <div key={day.date} className={styles.barItem}>
                      <div className={styles.barContainer}>
                        <div
                          className={styles.bar}
                          style={{ height: `${(day.tokens / maxDaily) * 100}%` }}
                        />
                      </div>
                      <div className={styles.barLabel}>{day.date.slice(5)}</div>
                      <div className={styles.barValue}>{formatNumber(day.tokens)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className={styles.tableSection}>
              <h3 className={styles.sectionTitle}>最近对话</h3>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>对话ID</th>
                      <th>模型</th>
                      <th>输入</th>
                      <th>输出</th>
                      <th>总计</th>
                      <th>时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usageRecords.length > 0 ? (
                      usageRecords.map((rec: TokenUsageRecord) => (
                        <tr key={rec.id}>
                          <td className={styles.idCell}>{rec.conversation_id || "—"}</td>
                          <td>{rec.model_name || "—"}</td>
                          <td>{formatNumber(rec.prompt_tokens)}</td>
                          <td>{formatNumber(rec.completion_tokens)}</td>
                          <td className={styles.totalCell}>{formatNumber(rec.total_tokens)}</td>
                          <td>{rec.created_at ? new Date(rec.created_at).toLocaleString("zh-CN") : "—"}</td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={6} className={styles.noData}>暂无数据</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
