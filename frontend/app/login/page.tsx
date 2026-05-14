"use client"

import { useState, FormEvent } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth"
import { Layers, Eye, EyeOff, Loader, AlertCircle, Check } from "lucide-react"
import styles from "./login.module.css"

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState(() => localStorage.getItem("docmind_remember") || "")
  const [password, setPassword] = useState("")
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [remember, setRemember] = useState(!!localStorage.getItem("docmind_remember"))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setError("")
    setLoading(true)
    try {
      await login(username.trim(), password)
      if (remember) {
        localStorage.setItem("docmind_remember", username)
      } else {
        localStorage.removeItem("docmind_remember")
      }
    } catch (err: any) {
      setError(err.message || "登录失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}><Layers size={28} /></div>
          <h1>DocMind</h1>
        </div>
        <p className={styles.subtitle}>智能文档问答系统</p>

        {error && (
          <div className={styles.error}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>用户名</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoFocus
              autoComplete="username"
            />
          </div>

          <div className={styles.field}>
            <label>密码</label>
            <div className={styles.pwdWrap}>
              <input
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
              />
              <button type="button" className={styles.pwdToggle} onClick={() => setShowPwd(!showPwd)}>
                {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.875rem", color: "#94a3b8" }}>
              <div style={{
                width: 18, height: 18, border: remember ? "none" : "1.5px solid #475569",
                borderRadius: 4, background: remember ? "#2563eb" : "transparent",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.15s",
              }}>
                {remember && <Check size={12} style={{ color: "#fff" }} />}
              </div>
              <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} style={{ display: "none" }} />
              记住密码
            </label>
          </div>

          <button type="submit" className={styles.submitBtn} disabled={loading || !username.trim() || !password}>
            {loading ? <Loader size={18} className={styles.spinning} /> : "登 录"}
          </button>
        </form>

        <p className={styles.footer}>
          还没有账号？<Link href="/register">立即注册</Link>
        </p>
      </div>
    </div>
  )
}
