"use client"

import { useState, FormEvent } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth"
import { Layers, Eye, EyeOff, Loader, AlertCircle } from "lucide-react"
import styles from "./login.module.css"

export default function RegisterPage() {
  const { register } = useAuth()
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    if (username.trim().length < 3) {
      setError("用户名至少 3 个字符")
      return
    }
    if (password.length < 6) {
      setError("密码至少 6 个字符")
      return
    }
    setError("")
    setLoading(true)
    try {
      await register(username.trim(), password, email.trim() || undefined)
    } catch (err: any) {
      setError(err.message || "注册失败")
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
        <p className={styles.subtitle}>创建新账号</p>

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
              placeholder="至少 3 个字符"
              autoFocus
              autoComplete="username"
            />
          </div>

          <div className={styles.field}>
            <label>邮箱（可选）</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="your@email.com"
              autoComplete="email"
            />
          </div>

          <div className={styles.field}>
            <label>密码</label>
            <div className={styles.pwdWrap}>
              <input
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="至少 6 个字符"
                autoComplete="new-password"
              />
              <button type="button" className={styles.pwdToggle} onClick={() => setShowPwd(!showPwd)}>
                {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button type="submit" className={styles.submitBtn} disabled={loading || !username.trim() || !password}>
            {loading ? <Loader size={18} className={styles.spinning} /> : "注 册"}
          </button>
        </form>

        <p className={styles.footer}>
          已有账号？<Link href="/login">去登录</Link>
        </p>
      </div>
    </div>
  )
}
