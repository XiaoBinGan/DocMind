"use client"

import { useState, FormEvent } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth"
import { Layers, Eye, EyeOff, Loader, AlertCircle } from "lucide-react"
import styles from "./login.module.css"

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setError("")
    setLoading(true)
    try {
      await login(username.trim(), password)
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
