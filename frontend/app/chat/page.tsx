"use client"

import { useState, useEffect, useRef, useCallback, memo } from "react"
import { useSearchParams } from "next/navigation"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import {
  Send, ChevronRight, FileText, MessageSquare,
  Trash2, Plus, BookOpen, Loader, Copy, Check
} from "lucide-react"
import { api, Document, Conversation, Message, Reference } from "@/lib/api"
import Nav from "@/components/nav"
import styles from "./page.module.css"

/* ================================================================
   Markdown 渲染器
   ================================================================ */
const MarkdownContent = memo(({ content, streaming = false }: { content: string; streaming?: boolean }) => (
  <div className={`${styles.md} ${streaming ? styles.mdStreaming : ""}`}>
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
      {content}
    </ReactMarkdown>
  </div>
))
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
  const [currentDocId, setCurrentDocId] = useState<string | null>(initialDocId)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamContent, setStreamContent] = useState("")
  const [statusText, setStatusText] = useState("")
  const [showDocList, setShowDocList] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamContentRef = useRef("")
  const streamingRefsRef = useRef<Reference[] | null>(null)

  useEffect(() => {
    loadDocuments()
    loadConversations()
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
      const result = await api.listConversations(currentDocId || undefined)
      setConversations(result.conversations)
    } catch (error) {
      console.error("Failed to load conversations:", error)
    }
  }

  const switchConversation = useCallback((conv: Conversation | null) => {
    setActiveConversation(conv)
    setMessages(conv?.messages ?? [])
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
          document_id: currentDocId || undefined
        },
        (chunk) => {
          streamContentRef.current += chunk
          setStreamContent(streamContentRef.current)
          setStatusText("正在思考...")
        },
        (messageId, conversationId, refs) => {
          streamingRefsRef.current = refs
          if (!activeConversation && conversationId) {
            switchConversation({
              id: conversationId,
              title: userMessage.slice(0, 50) + "...",
              document_id: currentDocId,
              messages: [],
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString()
            })
            loadConversations()
          }
        },
        (status) => setStatusText(status)
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

        <div className={styles.docSelector}>
          <button className={styles.docSelectorBtn} onClick={() => setShowDocList(!showDocList)}>
            <BookOpen size={16} />
            <span className={styles.docSelectorText}>
              {selectedDoc ? selectedDoc.name : "选择文档（可选）"}
            </span>
            <ChevronRight
              size={16}
              className={`${styles.docSelectorArrow} ${showDocList ? styles.docSelectorArrowOpen : ""}`}
            />
          </button>

          {showDocList && (
            <div className={styles.docList}>
              <button
                className={`${styles.docListItem} ${!currentDocId ? styles.docListItemActive : ""}`}
                onClick={() => { setCurrentDocId(null); setShowDocList(false); loadConversations() }}
              >
                <FileText size={14} />
                <span>通用对话</span>
              </button>
              {documents.filter(d => d.index_status === "ready").map(doc => (
                <button
                  key={doc.id}
                  className={`${styles.docListItem} ${currentDocId === doc.id ? styles.docListItemActive : ""}`}
                  onClick={() => { setCurrentDocId(doc.id); setShowDocList(false); loadConversations() }}
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
        </div>

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
              <p>{currentDocId ? "基于文档内容回答问题" : "选择左侧文档，或直接提问"}</p>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => (
                <div
                  key={msg.id || index}
                  className={`${styles.message} ${msg.role === "user" ? styles.userMessage : styles.assistantMessage}`}
                >
                  <div className={styles.messageAvatar}>
                    {msg.role === "user" ? "你" : "AI"}
                  </div>

                  <div className={styles.messageBody}>
                    <div className={styles.messageBubble}>
                      {msg.role === "user" ? (
                        <p className={styles.userText}>{msg.content}</p>
                      ) : (
                        <MarkdownContent content={msg.content} />
                      )}
                    </div>

                    {msg.role === "assistant" && (
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
                  <div className={styles.messageAvatar}>AI</div>
                  <div className={styles.messageBody}>
                    <div className={styles.messageBubble}>
                      <MarkdownContent content={streamContent} streaming />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

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
            {currentDocId ? "基于文档内容回答" : "AI 将根据上下文或通用知识回答"}
          </p>
        </div>
      </main>
      </div>
    </div>
  )
}
