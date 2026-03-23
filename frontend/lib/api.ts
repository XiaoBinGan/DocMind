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

export interface Reference {
  page: number
  reason: string
  preview: string
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  document_id?: string
  stream?: boolean
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
  async listConversations(documentId?: string): Promise<{ conversations: Conversation[]; total: number }> {
    const params = documentId ? `?document_id=${documentId}` : ""
    return this.request(`/api/conversations${params}`)
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
    onDone: (messageId: string, conversationId: string) => void,
    onStatus?: (status: string) => void
  ): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, stream: true }),
    })

    const reader = response.body?.getReader()
    if (!reader) throw new Error("No response body")

    const decoder = new TextDecoder()
    let buffer = ""
    let currentEvent = ""
    let messageId = ""
    let conversationId = ""

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
            onChunk(data)
          } else if (currentEvent === "done") {
            messageId = data
            onStatus?.("完成")
          } else if (currentEvent === "conversation_id") {
            conversationId = data
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
        if (currentEvent === "chunk") onChunk(data)
        else if (currentEvent === "done") { messageId = data; onStatus?.("完成") }
        else if (currentEvent === "conversation_id") conversationId = data
      }
    }

    onDone(messageId, conversationId)
  }
}

export const api = new ApiClient(API_BASE)
