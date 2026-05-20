"use client"

import { useAuth } from "@/lib/auth"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Layers } from "lucide-react"
import styles from "./nav.module.css"

export default function Nav() {
  const { user, logout } = useAuth()
  const pathname = usePathname()

  return (
    <nav className={styles.nav}>
      <div className={styles.left}>
        <Link href="/chat" className={styles.logo}>
          <span className={styles.logoIcon}><Layers size={20} /></span>
          <span className={styles.logoText}>DocMind</span>
        </Link>
        <div className={styles.links}>
          <Link href="/chat" className={`${styles.link} ${pathname === "/chat" ? styles.linkActive : ""}`}>
            对话
          </Link>
          <Link href="/documents" className={`${styles.link} ${pathname === "/documents" ? styles.linkActive : ""}`}>
            文档
          </Link>
          <Link href="/api-catalog" className={`${styles.link} ${pathname === "/api-catalog" ? styles.linkActive : ""}`}>
            API
          </Link>
          <Link href="/memory" className={`${styles.link} ${pathname === "/memory" ? styles.linkActive : ""}`}>
            记忆
          </Link>
          <Link href="/settings" className={`${styles.link} ${pathname === "/settings" ? styles.linkActive : ""}`}>
            设置
          </Link>
          <Link href="/token" className={`${styles.link} ${pathname === "/token" ? styles.linkActive : ""}`}>
            Token
          </Link>
          {user?.is_admin && (
            <Link href="/admin" className={`${styles.link} ${pathname === "/admin" ? styles.linkActive : ""}`}>
              管理
            </Link>
          )}
        </div>
      </div>
      <div className={styles.right}>
        <span className={styles.userName}>{user?.display_name || user?.username || ""}</span>
        <button className={styles.logoutBtn} onClick={logout} title="退出登录">
          退出
        </button>
      </div>
    </nav>
  )
}
