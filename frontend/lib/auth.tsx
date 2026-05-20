"use client"

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react"
import { useRouter, usePathname } from "next/navigation"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export interface UserInfo {
  id: string
  username: string
  email: string | null
  display_name: string | null
  avatar_url: string | null
  is_active: boolean
  is_admin: boolean
  created_at: string
  updated_at: string
}

interface AuthContextType {
  user: UserInfo | null
  token: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, email?: string) => Promise<void>
  logout: () => void
  updateUser: (data: { display_name?: string; email?: string }) => Promise<void>
  changePassword: (oldPwd: string, newPwd: string) => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be inside <AuthProvider>")
  return ctx
}

const PUBLIC_PATHS = ["/", "/login", "/register", "/api-catalog"]

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Init: restore token from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("docmind_token")
    if (saved) {
      setToken(saved)
      fetchUserInfo(saved)
    } else {
      setLoading(false)
    }
  }, [])

  // Redirect unauthenticated users
  useEffect(() => {
    if (loading) return
    if (!token && !PUBLIC_PATHS.includes(pathname)) {
      router.replace("/login")
    } else if (token && (pathname === "/login" || pathname === "/register")) {
      router.replace("/chat")
    }
  }, [token, loading, pathname, router])

  const fetchUserInfo = useCallback(async (t: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      })
      if (!res.ok) throw new Error("Token invalid")
      const data = await res.json()
      setUser(data)
    } catch {
      localStorage.removeItem("docmind_token")
      setToken(null)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "登录失败" }))
      throw new Error(data.detail || "登录失败")
    }
    const data = await res.json()
    localStorage.setItem("docmind_token", data.token)
    setToken(data.token)
    setUser(data.user)
    router.push("/")
  }, [router])

  const register = useCallback(async (username: string, password: string, email?: string) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, email }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "注册失败" }))
      throw new Error(data.detail || "注册失败")
    }
    const data = await res.json()
    localStorage.setItem("docmind_token", data.token)
    setToken(data.token)
    setUser(data.user)
    router.push("/")
  }, [router])

  const logout = useCallback(() => {
    localStorage.removeItem("docmind_token")
    setToken(null)
    setUser(null)
    router.push("/login")
  }, [router])

  const updateUser = useCallback(async (data: { display_name?: string; email?: string }) => {
    if (!token) throw new Error("Not authenticated")
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error("Update failed")
    const updated = await res.json()
    setUser(updated)
  }, [token])

  const changePassword = useCallback(async (oldPwd: string, newPwd: string) => {
    if (!token) throw new Error("Not authenticated")
    const res = await fetch(`${API_BASE}/api/auth/change-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "修改失败" }))
      throw new Error(data.detail || "修改失败")
    }
  }, [token])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, updateUser, changePassword }}>
      {children}
    </AuthContext.Provider>
  )
}
