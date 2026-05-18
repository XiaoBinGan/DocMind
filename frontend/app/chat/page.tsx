"use client"

import { useState, useEffect, useRef, useCallback, memo, useMemo } from "react"
import { useSearchParams } from "next/navigation"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import {
  Send, FileText, MessageSquare,
  Trash2, Plus, BookOpen, Loader, Copy, Check
} from "lucide-react"
import { api, Document, Conversation, Message, Reference, IntentResult } from "@/lib/api"
import Nav from "@/components/nav"
import { rehypeMermaidBlock } from "@/app/components/chat/rehype-mermaid-block"
import dynamic from "next/dynamic"
import styles from "./page.module.css"

// Dynamic import MermaidBlock to avoid SSR issues
const MermaidBlock = dynamic(
  () => import("@/app/components/chat/mermaid-block"),
  { ssr: false }
)

/* ================================================================
   Markdown 渲染器
   ================================================================ */

const INTENT_LABELS: Record<string, { label: string; color: string }> = {
  doc_query: { label: "文档查询", color: "#00c9ff" },
  general_chat: { label: "通用对话", color: "#10b981" },
  doc_comparison: { label: "文档对比", color: "#f59e0b" },
  ambiguous: { label: "待定", color: "#8b5cf6" },
}

/**
 * Streaming markdown preprocessing:
 * - Closes unclosed code fences so partial blocks render correctly
 * - Ensures trailing newlines don't create empty paragraphs
 */
function prepareStreamingMarkdown(content: string): string {
  if (!content) return content
  // Count code fence markers (```) to detect unclosed blocks
  // Match lines that start with ``` (possibly followed by a language tag)
  const fenceMatches = content.match(/^```[\w]*\s*$/gm)
  const fenceCount = fenceMatches ? fenceMatches.length : 0
  if (fenceCount % 2 !== 0) {
    // Odd number of fences → the last fence is an unclosed opening block
    // Append a closing fence so the markdown parser renders it correctly
    const lastFenceIdx = content.lastIndexOf("```")
    const afterLastFence = content.substring(lastFenceIdx + 3).trimStart()
    // Only close if the content after the last fence doesn't already have a closing fence
    // (e.g. the stream just arrived a complete block)
    if (!afterLastFence.startsWith("```")) {
      content += "\n```"
    }
  }
  return content
}

// Custom code component to handle mermaid blocks
const CodeBlock = memo(({ className, children, ...props }: any) => {
  const isMermaid = props["dataMermaid"]
  const codeStr = String(children).replace(/\n$/, "")

  if (isMermaid) {
    return <MermaidBlock code={codeStr} />
  }

  return (
    <code className={className} {...props}>
      {children}
    </code>
  )
})
CodeBlock.displayName = "CodeBlock"

// Custom pre component to pass through mermaid data attribute
const PreBlock = memo(({ children, ...props }: any) => {
  if (props["dataMermaid"]) {
    return <>{children}</>
  }
  return <pre {...props}>{children}</pre>
})
PreBlock.displayName = "PreBlock"

const markdownComponents: Components = {
  code: CodeBlock,
  pre: PreBlock,
}

const rehypePlugins = [rehypeHighlight, rehypeMermaidBlock]

const MarkdownContent = memo(({ content, streaming = false }: { content: string; streaming?: boolean }) => {
  const processed = streaming ? prepareStreamingMarkdown(content) : content
  return (
    <div className={`${styles.md} ${streaming ? styles.mdStreaming : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={rehypePlugins}
        components={markdownComponents}
      >
        {processed}
      </ReactMarkdown>
    </div>
  )
})
MarkdownContent.displayName = "MarkdownContent"

/* ================================================================
   主页面
   ================================================================ */
export default function ChatPage() {
  const searchParams = useSearchParams()
  const initialDocId = searchParams.get("doc")

  const [documents, setDocuments] = useState<Document[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null)
  const [activeConvId, setActiveConvId] = useState<string | null>(
    typeof window !== "undefined" ? localStorage.getItem("docmind_active_conv_id") : null
  )
  const [currentDocId, setCurrentDocId] = useState<string | null>(initialDocId)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamContent, setStreamContent] = useState("")
  const [statusText, setStatusText] = useState("")
  const [showDocList, setShowDocList] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const formatTime = (iso?: string) => {
    if (!iso) return ""
    const d = new Date(iso)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  const [lastIntent, setLastIntent] = useState<IntentResult | null>(null)
  const [chatMode, setChatMode] = useState<"general" | "doc_chat">("general")

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamContentRef = useRef("")
  const streamingRefsRef = useRef<Reference[] | null>(null)
  const activeConvRef = useRef<Conversation | null>(null)

  // 保持 ref 与 state 同步
  useEffect(() => {
    activeConvRef.current = activeConversation
  }, [activeConversation])

  useEffect(() => {
    loadDocuments()
    loadConversations()
    // 恢复上次活跃的对话
    if (activeConvId) {
      setTimeout(async () => {
        try {
          const result = await api.getConversation(activeConvId)
          setActiveConversation(result)
          setMessages(result.messages || [])
        } catch (e) {
          console.error("Failed to restore conversation:", e)
          localStorage.removeItem("docmind_active_conv_id")
        }
      }, 100)
    }
  }, [])

  const loadDocuments = async () => {
    try {
      const result = await api.listDocuments()
      setDocuments(result.documents)
    } catch (error) {
      console.error("Failed to load documents:", error)
    }
  }

  const loadConversations = async () => {
    try {
      if (chatMode === "general") {
        const result = await api.listConversations(undefined, "general")
        setConversations(result.conversations)
      } else if (currentDocId) {
        const result = await api.listConversations(currentDocId)
        setConversations(result.conversations)
      } else {
        const result = await api.listConversations(undefined, "doc_chat")
        setConversations(result.conversations)
      }
    } catch (error) {
      console.error("Failed to load conversations:", error)
    }
  }

  const switchConversation = useCallback((conv: Conversation | null) => {
    setActiveConversation(conv)
    setActiveConvId(conv?.id || null)
    if (conv) {
      localStorage.setItem("docmind_active_conv_id", conv.id)
    } else {
      localStorage.removeItem("docmind_active_conv_id")
    }
    setMessages(conv?.messages ?? [])
    setLastIntent(null)
    setStreamContent("")
  }, [])

  // 仅在流式输出中或新增消息时滚动到底部，流结束后不滚动
  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" })
  }, [])

  useEffect(() => {
    if (streamContent) {
      scrollToBottom()
    }
  }, [streamContent, scrollToBottom])

  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom(false)
    }
  }, [messages.length, scrollToBottom])

  useEffect(() => {
    if (currentDocId) loadConversations()
  }, [currentDocId])

  useEffect(() => {
    loadConversations()
  }, [chatMode])

  // 切换模式/文档时，如果旧对话不匹配则清除
  useEffect(() => {
    if (activeConversation) {
      const isGeneral = activeConversation.chat_type === 'general'
      const isDocChat = activeConversation.chat_type === 'doc_chat'
      const modeMatches = chatMode === 'general' ? isGeneral : isDocChat
      const docMatches = currentDocId ? activeConversation.document_id === currentDocId : !activeConversation.document_id
      if (!modeMatches || !docMatches) {
        switchConversation(null)
      }
    }
  }, [chatMode, currentDocId])

  const handleCopy = useCallback(async (msgId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedId(msgId)
      setTimeout(() => setCopiedId(null), 2000)
    } catch { /* ignore */ }
  }, [])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 200) + "px"
  }, [])

  const handleSend = async () => {
    if (!input.trim() || loading || streaming) return

    const userMessage = input.trim()
    setInput("")
    if (inputRef.current) inputRef.current.style.height = "auto"
    setLoading(true)
    setStreaming(true)
    setStreamContent("")
    setStatusText("正在连接...")
    setLastIntent(null)

    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: userMessage,
      references: null,
      created_at: new Date().toISOString()
    }
    setMessages(prev => [...prev, tempUserMsg])

    try {
      streamContentRef.current = ""
      streamingRefsRef.current = null

      await api.chatStream(
        {
          message: userMessage,
          conversation_id: activeConversation?.id || undefined,
          document_id: currentDocId || undefined,
          chat_type: chatMode
        },
        (chunk) => {
          streamContentRef.current += chunk
          setStreamContent(streamContentRef.current)
          setStatusText("正在思考...")
        },
        (messageId, conversationId, refs) => {
          streamingRefsRef.current = refs
          if (!activeConvRef.current && conversationId) {
            switchConversation({
              id: conversationId,
              title: userMessage.slice(0, 50) + "...",
              document_id: currentDocId,
              chat_type: chatMode,
              messages: [],
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString()
            })
            loadConversations()
          }
        },
        (status) => setStatusText(status),
        (intent) => setLastIntent(intent)
      )

      const assistantMsg: Message = {
        id: `completed-${Date.now()}`,
        role: "assistant",
        content: streamContentRef.current || "（无回复）",
        references: streamingRefsRef.current,
        created_at: new Date().toISOString()
      }

      setMessages(prev => {
        const filtered = prev.filter(m => m.id !== tempUserMsg.id)
        return [...filtered, tempUserMsg, assistantMsg]
      })

      loadConversations()
      setStatusText("")
    } catch (error) {
      console.error("Chat error:", error)
      const errorMsg: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: "抱歉，发生了错误。请稍后重试。",
        references: null,
        created_at: new Date().toISOString()
      }
      setMessages(prev => [...prev.filter(m => m.id !== tempUserMsg.id), tempUserMsg, errorMsg])
      setStatusText("")
    } finally {
      setLoading(false)
      setStreaming(false)
      setStreamContent("")
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    switchConversation(null)
    setLastIntent(null)
    setStreamContent("")
    streamingRefsRef.current = null
  }

  const handleDeleteConversation = async (id: string) => {
    try {
      await api.deleteConversation(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (activeConversation?.id === id) {
        switchConversation(null)
      }
    } catch (error) {
      console.error("Delete failed:", error)
    }
  }

  const selectedDoc = documents.find(d => d.id === currentDocId)

  return (
    <div className={styles.container}>
      <Nav />
      <div className={styles.body}>
      <div className={styles.bgGradient} />

      {/* 侧边栏 */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2 className={styles.sidebarTitle}>
            <MessageSquare size={18} />
            对话
          </h2>
          <button className={styles.newChatBtn} onClick={handleNewChat} title="新对话">
            <Plus size={18} />
          </button>
        </div>

        {/* 模式切换 Tab */}
        <div className={styles.modeTabs}>
          <button
            className={`${styles.modeTab} ${chatMode === "general" ? styles.modeTabActive : ""}`}
            onClick={() => {
              setChatMode("general")
              setCurrentDocId(null)
              setShowDocList(false)
              setActiveConversation(null)
              setActiveConvId(null)
              setMessages([])
              setLastIntent(null)
              localStorage.removeItem("docmind_active_conv_id")
            }}
          >
            <MessageSquare size={14} />
            通用聊天
          </button>
          <button
            className={`${styles.modeTab} ${chatMode === "doc_chat" ? styles.modeTabActive : ""}`}
            onClick={() => {
              setChatMode("doc_chat")
              setShowDocList(true)
              setActiveConversation(null)
              setActiveConvId(null)
              setMessages([])
              setLastIntent(null)
              localStorage.removeItem("docmind_active_conv_id")
            }}
          >
            <BookOpen size={14} />
            知识库
          </button>
        </div>

        {/* 知识库文档选择器 */}
        {showDocList && (
          <div className={styles.docList}>
            {documents.filter(d => d.index_status === "ready").map(doc => (
              <button
                key={doc.id}
                className={`${styles.docListItem} ${currentDocId === doc.id ? styles.docListItemActive : ""}`}
                onClick={() => { setCurrentDocId(doc.id); setShowDocList(false); switchConversation(null) }}
              >
                <FileText size={14} />
                <span>{doc.name}</span>
              </button>
            ))}
            {documents.filter(d => d.index_status === "ready").length === 0 && (
              <p className={styles.docListEmpty}>暂无已索引的文档</p>
            )}
          </div>
        )}

        {/* 当前知识库文档指示器 */}
        {currentDocId && (
          <div className={styles.currentDocIndicator}>
            <FileText size={14} />
            <span className={styles.currentDocName}>{selectedDoc?.name || "加载中..."}</span>
            <button
              className={styles.currentDocClear}
              onClick={() => { setCurrentDocId(null); switchConversation(null) }}
              title="切换回通用聊天"
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}

        <div className={styles.conversationsList}>
          {conversations.map(conv => (
            <div
              key={conv.id}
              className={`${styles.conversationItem} ${activeConversation?.id === conv.id ? styles.conversationItemActive : ""}`}
              onClick={() => switchConversation(conv)}
            >
              <MessageSquare size={14} className={styles.convIcon} />
              <span className={styles.convTitle}>{conv.title}</span>
              <button
                className={styles.convDelete}
                onClick={(e) => { e.stopPropagation(); handleDeleteConversation(conv.id) }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <p className={styles.noConversations}>暂无对话记录</p>
          )}
        </div>
      </aside>

      {/* 主聊天区 */}
      <main className={styles.main}>
        {selectedDoc && (
          <div className={styles.docIndicator}>
            <FileText size={14} />
            <span>{selectedDoc.name}</span>
            <button onClick={() => { setCurrentDocId(null); loadConversations() }}>
              <Trash2 size={12} />
            </button>
          </div>
        )}

        <div className={styles.messages}>
          {!activeConversation && messages.length === 0 ? (
            <div className={styles.welcome}>
              <div className={styles.welcomeIcon}>
                <MessageSquare size={48} />
              </div>
              <h2>开始对话</h2>
              <p>{chatMode === "general" ? "通用 AI 对话" : currentDocId ? "基于文档内容回答问题" : "选择左侧文档，或直接提问"}</p>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => (
                <div
                  key={msg.id || index}
                  className={`${styles.message} ${msg.role === "user" ? styles.userMessage : styles.assistantMessage}`}
                >
                  <div className={styles.messageBody}>
                    <div className={styles.messageBubble}>
                      {msg.role === "user" ? (
                        <p className={styles.userText}>{msg.content}</p>
                      ) : (
                        <MarkdownContent content={msg.content} />
                      )}
                    </div>

                    <div className={styles.messageTime}>
                      {formatTime(msg.created_at)}
                    </div>

                    {msg.role === "assistant" && chatMode !== "general" && (
                      <div className={styles.references}>
                        <span className={styles.refLabel}>引用：</span>
                        {msg.references && msg.references.length > 0
                          ? msg.references.map((ref, i) => (
                              <span key={i} className={styles.refBadge}>P{ref.page}</span>
                            ))
                          : <span className={styles.refNone}>无</span>}
                      </div>
                    )}

                    {msg.role === "assistant" && (
                      <div className={styles.messageActions}>
                        <button
                          className={styles.actionBtn}
                          onClick={() => handleCopy(msg.id, msg.content)}
                          title="复制"
                        >
                          {copiedId === msg.id ? <Check size={14} /> : <Copy size={14} />}
                          <span>{copiedId === msg.id ? "已复制" : "复制"}</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {streaming && streamContent && (
                <div className={`${styles.message} ${styles.assistantMessage}`}>
                  <div className={styles.messageBody}>
                    <div className={styles.messageBubble}>
                      <MarkdownContent content={streamContent} streaming />
                    </div>
                  </div>
                </div>
              )}

              {/* 意图识别展示 — 已移到输入框上方 */}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 意图识别状态栏 — 固定在输入框上方 */}
        {lastIntent && chatMode !== "general" && (
          <div className={styles.intentBar}>
            <span
              className={styles.intentDot}
              style={{ backgroundColor: INTENT_LABELS[lastIntent.intent_type]?.color || "#8b5cf6" }}
            />
            <span className={styles.intentLabel}>
              {INTENT_LABELS[lastIntent.intent_type]?.label || lastIntent.intent_type}
            </span>
            <span className={styles.intentConfidence}>
              置信度 {(lastIntent.confidence * 100).toFixed(0)}%
            </span>
            {lastIntent.keywords.length > 0 && (
              <span className={styles.intentKeywords}>
                {lastIntent.keywords.slice(0, 3).map(k => (
                  <span key={k} className={styles.intentKeyword}>{k}</span>
                ))}
              </span>
            )}
            {lastIntent.intent_type === "doc_query" && !currentDocId && (
              <span className={styles.intentHint}>💡 已自动匹配知识库</span>
            )}
          </div>
        )}

        {statusText && (
          <div className={styles.statusBar}>
            <Loader size={14} className={styles.statusSpinner} />
            <span>{statusText}</span>
          </div>
        )}

        <div className={styles.inputArea}>
          <div className={styles.inputWrapper}>
            <textarea
              ref={inputRef}
              className={styles.input}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="输入你的问题... (Enter 发送，Shift+Enter 换行)"
              rows={1}
              disabled={loading}
            />
            <button
              className={styles.sendBtn}
              onClick={handleSend}
              disabled={!input.trim() || loading}
            >
              {loading ? <Loader size={20} className={styles.spinning} /> : <Send size={20} />}
            </button>
          </div>
          <p className={styles.inputHint}>
            {chatMode === "general" ? "通用 AI 对话，不引用文档" : currentDocId ? "基于文档内容回答" : "AI 将自动匹配知识库或使用通用知识回答"}
          </p>
        </div>
      </main>
      </div>
    </div>
  )
}
