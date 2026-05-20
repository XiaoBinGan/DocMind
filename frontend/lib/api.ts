const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export interface Document {
  id: string
  name: string
  file_type: string
  file_size: number
  page_count: number
  index_status: "pending" | "indexing" | "ready" | "error"
  index_tree: IndexNode | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface IndexNode {
  id: string
  title: string
  page_start: number
  page_end: number
  level: number
  content_summary?: string
  children: IndexNode[]
}

export interface Conversation {
  id: string
  title: string
  document_id: string | null
  chat_type: string
  messages: Message[]
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  references: Reference[] | null
  created_at: string
}

export interface IntentResult {
  intent_type: string  // doc_query | general_chat | doc_comparison | ambiguous
  confidence: number
  keywords: string[]
  matched_document_ids?: string[]
  reasoning: string
}

export interface Reference {
  page: number
  reason: string
  preview: string
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  document_id?: string
  chat_type?: "general" | "doc_chat"
  stream?: boolean
}

// ── Memory types ──
export interface Memory {
  id: string
  user_id: string
  category: "daily" | "long_term" | "preference" | "decision" | "lesson"
  content: string
  source: string | null
  source_id: string | null
  tags: string[] | null
  importance: number
  is_archived: number
  created_at: string
  updated_at: string
}

export interface MemoryStats {
  total: number
  by_category: Record<string, number>
  archived: number
  active: number
}

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("docmind_token") : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        ...getAuthHeaders(),
        ...options?.headers,
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Request failed" }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    return response.json()
  }

  // Documents API
  async uploadDocument(file: File, onProgress?: (progress: number) => void): Promise<Document> {
    const formData = new FormData()
    formData.append("file", file)
    const token = typeof window !== "undefined" ? localStorage.getItem("docmind_token") : null

    const xhr = new XMLHttpRequest()
    
    return new Promise((resolve, reject) => {
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress((e.loaded / e.total) * 100)
        }
      })
      
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText))
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`))
        }
      })
      
      xhr.addEventListener("error", () => reject(new Error("Upload failed")))
      
      xhr.open("POST", `${this.baseUrl}/api/documents/upload`)
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`)
      xhr.send(formData)
    })
  }

  async listDocuments(): Promise<{ documents: Document[]; total: number }> {
    return this.request("/api/documents")
  }

  async getDocument(id: string): Promise<Document> {
    return this.request(`/api/documents/${id}`)
  }

  async deleteDocument(id: string): Promise<void> {
    await this.request(`/api/documents/${id}`, { method: "DELETE" })
  }

  async reindexDocument(id: string): Promise<void> {
    await this.request(`/api/documents/${id}/reindex`, { method: "POST" })
  }

  // Conversations API
  async listConversations(documentId?: string, chatType?: string): Promise<{ conversations: Conversation[]; total: number }> {
    const params = new URLSearchParams()
    if (documentId) params.set("document_id", documentId)
    if (chatType) params.set("chat_type", chatType)
    const qs = params.toString()
    return this.request(`/api/conversations${qs ? "?" + qs : ""}`)
  }

  async getConversation(id: string): Promise<Conversation> {
    return this.request(`/api/conversations/${id}`)
  }

  async deleteConversation(id: string): Promise<void> {
    await this.request(`/api/conversations/${id}`, { method: "DELETE" })
  }

  // Chat API
  async chat(request: ChatRequest): Promise<{ conversation_id: string; message: Message }> {
    return this.request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    })
  }

  // Streaming chat
  async chatStream(
    request: ChatRequest,
    onChunk: (chunk: string) => void,
    onDone: (messageId: string, conversationId: string, references: Reference[] | null) => void,
    onStatus?: (status: string) => void,
    onIntent?: (intent: IntentResult) => void
  ): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ ...request, stream: true }),
    })

    const reader = response.body?.getReader()
    if (!reader) throw new Error("No response body")

    const decoder = new TextDecoder()
    let buffer = ""
    let currentEvent = ""
    let messageId = ""
    let conversationId = ""
    let references: Reference[] | null = null
    let intent: IntentResult | null = null
    let doneReceived = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim()
          continue
        }
        if (line.startsWith("data:")) {
          const data = line.slice(5).trim()
          if (!data) continue

          if (currentEvent === "chunk") {
            // Backend sends JSON-encoded chunk: {"t": "..."}
            // JSON decoding preserves newlines inside the text.
            try {
              const parsed = JSON.parse(data)
              onChunk(parsed.t || "")
            } catch {
              onChunk(data)
            }
          }
          if (currentEvent === "references") {
            try { references = JSON.parse(data) } catch { references = null }
          } else if (currentEvent === "intent") {
            try { 
              const parsed = JSON.parse(data)
              intent = parsed
              onIntent?.(parsed)
            } catch { intent = null }
          } else if (currentEvent === "done") {
            messageId = data
            doneReceived = true
            onStatus?.("完成")
          } else if (currentEvent === "conversation_id") {
            conversationId = data
            if (doneReceived) {
              onDone(messageId, conversationId, references)
            }
          }
        }
      }
    }

    // Process remaining buffer
    const finalLines = buffer.split("\n")
    for (let i = 0; i < finalLines.length; i++) {
      if (finalLines[i].startsWith("event:")) {
        currentEvent = finalLines[i].slice(6).trim()
        continue
      }
      if (finalLines[i].startsWith("data:")) {
        const data = finalLines[i].slice(5).trim()
        if (!data) continue
        if (currentEvent === "chunk") {
          try {
            const parsed = JSON.parse(data)
            onChunk(parsed.t || "")
          } catch {
            onChunk(data)
          }
        }
        if (currentEvent === "references") {
          try { references = JSON.parse(data) } catch { references = null }
        }
        else if (currentEvent === "intent") {
          try { 
            const parsed = JSON.parse(data)
            intent = parsed
            onIntent?.(parsed)
          } catch { intent = null }
        }
        else if (currentEvent === "done") { 
          messageId = data
          doneReceived = true
          onStatus?.("完成") 
        }
        else if (currentEvent === "conversation_id") { 
          conversationId = data
          if (doneReceived) {
            onDone(messageId, conversationId, references)
          }
        }
      }
    }

    // 确保 onDone 被调用
    onDone(messageId, conversationId, references)
  }

  // ── Memories API ──
  async getMemoryStats(): Promise<MemoryStats> {
    return this.request("/api/memories/stats")
  }

  async listMemories(params?: {
    category?: string
    is_archived?: number
    search?: string
    page?: number
    page_size?: number
  }): Promise<{ memories: Memory[]; total: number }> {
    const sp = new URLSearchParams()
    if (params?.category) sp.set("category", params.category)
    if (params?.is_archived !== undefined) sp.set("is_archived", String(params.is_archived))
    if (params?.search) sp.set("search", params.search)
    if (params?.page) sp.set("page", String(params.page))
    if (params?.page_size) sp.set("page_size", String(params.page_size))
    const qs = sp.toString()
    return this.request(`/api/memories${qs ? `?${qs}` : ""}`)
  }

  async createMemory(data: {
    content: string
    category?: string
    source?: string
    tags?: string[]
    importance?: number
  }): Promise<Memory> {
    return this.request("/api/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
  }

  async updateMemory(id: string, data: {
    content?: string
    category?: string
    tags?: string[]
    importance?: number
    is_archived?: number
  }): Promise<Memory> {
    return this.request(`/api/memories/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
  }

  async deleteMemory(id: string): Promise<void> {
    await this.request(`/api/memories/${id}`, { method: "DELETE" })
  }

  // ── Admin API ──
  async getAdminUsers(): Promise<AdminUser[]> {
    return this.request("/api/auth/admin/users")
  }

  async updateAdminUser(userId: string, action: string): Promise<any> {
    return this.request(`/api/auth/admin/users/${userId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    })
  }

  async getAdminConversations(userId?: string, page = 1): Promise<{ conversations: AdminConversation[]; total: number; page: number }> {
    const params = new URLSearchParams({ page: String(page) })
    if (userId) params.set("user_id", userId)
    return this.request(`/api/auth/admin/conversations?${params}`)
  }

  async getAdminConversationDetail(convId: string): Promise<AdminConversationDetail> {
    return this.request(`/api/auth/admin/conversations/${convId}`)
  }

  // ── Token API ──
  async getTokenUsage(days = 30, limit = 100): Promise<TokenUsageRecord[]> {
    return this.request(`/api/token/my-usage?days=${days}&limit=${limit}`)
  }

  async getTokenSummary(days = 30): Promise<TokenSummary> {
    return this.request(`/api/token/my-summary?days=${days}`)
  }

  async getAdminTokenUsage(userId?: string, days = 30, page = 1, pageSize = 50): Promise<{ records: TokenUsageRecord[]; total: number }> {
    const params = new URLSearchParams({ days: String(days), page: String(page), page_size: String(pageSize) })
    if (userId) params.set('user_id', userId)
    return this.request(`/api/token/admin/usage?${params}`)
  }

  async getAdminTokenSummary(userId?: string, days = 30): Promise<UserTokenSummary[]> {
    const params = new URLSearchParams({ days: String(days) })
    if (userId) params.set('user_id', userId)
    return this.request(`/api/token/admin/summary?${params}`)
  }

  async getTokenUsageCount(userId: string, days = 30): Promise<{ total_tokens: number; turn_count: number }> {
    const params = new URLSearchParams({ days: String(days) })
    params.set('user_id', userId)
    const result = await this.request(`/api/token/admin/summary?${params}`) as UserTokenSummary[]
    if (result.length > 0) return {
      total_tokens: result[0].total_tokens,
      turn_count: result[0].turn_count,
    }
    return { total_tokens: 0, turn_count: 0 }
  }
}

// ── Admin types ──
export interface AdminUser {
  id: string
  username: string
  email: string | null
  display_name: string | null
  is_active: boolean
  is_admin: boolean
  conversation_count: number
  created_at: string
  updated_at: string
}

export interface AdminConversation {
  id: string
  title: string
  user_id: string | null
  chat_type: string
  document_id: string | null
  message_count: number
  created_at: string
  updated_at: string
}

export interface AdminConversationDetail {
  id: string
  title: string
  user_id: string | null
  chat_type: string
  document_id: string | null
  messages: Array<{
    id: string
    role: string
    content: string
    references: any
    created_at: string
  }>
  created_at: string
  updated_at: string
}

// ── Token types ──
export interface TokenUsageRecord {
  id: string
  user_id: string
  username: string | null
  conversation_id: string | null
  model_name: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  created_at: string | null
}

export interface TokenDailyStat {
  date: string
  tokens: number
  turns: number
}

export interface TokenSummary {
  total_prompt: number
  total_completion: number
  total_all: number
  turn_count: number
  daily: TokenDailyStat[]
}

export interface UserTokenSummary {
  user_id: string
  username: string
  display_name: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  turn_count: number
}

export const api = new ApiClient(API_BASE)

// ── API Catalog types ──
export interface ApiDefinition {
  id: string
  name: string
  description: string
  base_url: string
  method: string
  path: string
  headers: Record<string, string>
  body_schema: Record<string, unknown>
  auth_type: string
  auth_header: string
  timeout_ms: number
  enabled: number
  example_queries: string[]
  expected_response: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  created_by: string
}

export interface ChainMember {
  id: string
  order: number
  api_id: string
  api_name: string
  input_mapping: Record<string, unknown>
  output_mapping: Record<string, unknown>
  created_at: string | null
}

export interface SerialChain {
  id: string
  name: string
  description: string
  steps_count: number
  enabled: number
  members: ChainMember[]
  created_at: string | null
  updated_at: string | null
  created_by: string
}

export interface IntentSuggestion {
  type: string
  confidence: number
  target_id: string | null
  target_name: string
  explanation: string
  example_queries: string[]
}

// ── API Catalog methods ──
const API_CATALOG_BASE = "/api-catalog"

export const apiCatalog = {
  async list(): Promise<ApiDefinition[]> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async get(id: string): Promise<ApiDefinition> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/${id}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async create(data: Record<string, unknown>): Promise<ApiDefinition> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async update(id: string, data: Record<string, unknown>): Promise<ApiDefinition> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async delete(id: string): Promise<{ deleted: boolean }> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/${id}`, {
      method: "DELETE",
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async toggle(id: string, enabled: boolean): Promise<ApiDefinition> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/${id}/toggle?enabled=${enabled}`, {
      method: "PATCH",
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async search(keyword: string): Promise<ApiDefinition[]> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/search?keyword=${encodeURIComponent(keyword)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  // ── 智能推荐 ──
  async suggest(query: string): Promise<{ suggestions: IntentSuggestion[] }> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/suggest?query=${encodeURIComponent(query)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },
}

// ── Chains methods ──
export const chains = {
  async list(): Promise<SerialChain[]> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async get(id: string): Promise<SerialChain> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains/${id}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async create(data: Record<string, unknown>): Promise<SerialChain> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async update(id: string, data: Record<string, unknown>): Promise<SerialChain> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async delete(id: string): Promise<{ deleted: boolean }> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains/${id}`, {
      method: "DELETE",
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },

  async execute(id: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    const resp = await fetch(`${API_BASE}${API_CATALOG_BASE}/chains/${id}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_data: input }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.json()
  },
}
