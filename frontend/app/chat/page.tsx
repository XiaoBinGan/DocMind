"use client"

import { useState, useEffect, useRef } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { Send, ChevronRight, FileText, MessageSquare, Trash2, Plus, BookOpen, Loader } from "lucide-react"
import { api, Document, Conversation, Message } from "@/lib/api"
import styles from "./page.module.css"

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
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamContentRef = useRef("")

  // Load documents and conversations
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

  // Load active conversation
  useEffect(() => {
    if (activeConversation) {
      setMessages(activeConversation.messages)
    } else {
      setMessages([])
    }
  }, [activeConversation])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamContent])

  // Handle document selection
  useEffect(() => {
    if (currentDocId) {
      loadConversations()
    }
  }, [currentDocId])

  const handleSend = async () => {
    if (!input.trim() || loading || streaming) return

    const userMessage = input.trim()
    setInput("")
    setLoading(true)
    setStreaming(true)
    setStreamContent("")
    setStatusText("正在连接...")

    // Optimistically add user message
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
      
      await api.chatStream(
        { message: userMessage, conversation_id: activeConversation?.id || undefined, document_id: currentDocId || undefined },
        (chunk) => {
          streamContentRef.current += chunk
          setStreamContent(prev => prev + chunk)
          setStatusText("正在思考...")
        },
        (messageId, conversationId) => {
          // Conversation created/updated
          if (!activeConversation && conversationId) {
            setActiveConversation({
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

      // Add completed message
      const assistantMsg: Message = {
        id: `completed-${Date.now()}`,
        role: "assistant",
        content: streamContentRef.current || "（无回复）",
        references: null,
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

  const handleNewChat = async () => {
    setActiveConversation(null)
    setMessages([])
  }

  const handleDeleteConversation = async (id: string) => {
    try {
      await api.deleteConversation(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (activeConversation?.id === id) {
        setActiveConversation(null)
        setMessages([])
      }
    } catch (error) {
      console.error("Delete failed:", error)
    }
  }

  const selectedDoc = documents.find(d => d.id === currentDocId)

  return (
    <div className={styles.container}>
      {/* Background Effects */}
      <div className={styles.bgGradient} />
      
      {/* Sidebar */}
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

        {/* Document selector */}
        <div className={styles.docSelector}>
          <button 
            className={styles.docSelectorBtn}
            onClick={() => setShowDocList(!showDocList)}
          >
            <BookOpen size={16} />
            <span className={styles.docSelectorText}>
              {selectedDoc ? selectedDoc.name : "选择文档（可选）"}
            </span>
            <ChevronRight size={16} className={`${styles.docSelectorArrow} ${showDocList ? styles.docSelectorArrowOpen : ""}`} />
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

        {/* Conversations list */}
        <div className={styles.conversationsList}>
          {conversations.map(conv => (
            <div 
              key={conv.id}
              className={`${styles.conversationItem} ${activeConversation?.id === conv.id ? styles.conversationItemActive : ""}`}
              onClick={() => setActiveConversation(conv)}
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

      {/* Main Chat Area */}
      <main className={styles.main}>
        {/* Current document indicator */}
        {selectedDoc && (
          <div className={styles.docIndicator}>
            <FileText size={14} />
            <span>{selectedDoc.name}</span>
            <button onClick={() => { setCurrentDocId(null); loadConversations() }}>
              <Trash2 size={12} />
            </button>
          </div>
        )}

        {/* Messages */}
        <div className={styles.messages}>
          {!activeConversation && messages.length === 0 ? (
            <div className={styles.welcome}>
              <div className={styles.welcomeIcon}>
                <MessageSquare size={48} />
              </div>
              <h2>开始对话</h2>
              <p>
                {currentDocId 
                  ? "基于文档内容回答问题" 
                  : "选择左侧文档，或直接提问"}
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg, index) => (
                <div 
                  key={msg.id || index}
                  className={`${styles.message} ${msg.role === "user" ? styles.userMessage : styles.assistantMessage}`}
                >
                  <div className={styles.messageBubble}>
                    {msg.content}
                    {msg.references && msg.references.length > 0 && (
                      <div className={styles.references}>
                        <span className={styles.refLabel}>引用：</span>
                        {msg.references.map((ref, i) => (
                          <span key={i} className={styles.refBadge}>
                            P{ref.page}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              
              {/* Streaming message */}
              {streaming && streamContent && (
                <div className={`${styles.message} ${styles.assistantMessage}`}>
                  <div className={styles.messageBubble}>
                    {streamContent}
                    <span className={styles.cursor}>|</span>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Status indicator */}
        {statusText && (
          <div className={styles.statusBar}>
            <Loader size={14} className={styles.statusSpinner} />
            <span>{statusText}</span>
          </div>
        )}

        {/* Input */}
        <div className={styles.inputArea}>
          <div className={styles.inputWrapper}>
            <textarea
              ref={inputRef}
              className={styles.input}
              value={input}
              onChange={(e) => setInput(e.target.value)}
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
              {loading ? (
                <Loader size={20} className={styles.spinning} />
              ) : (
                <Send size={20} />
              )}
            </button>
          </div>
          <p className={styles.inputHint}>
            {currentDocId 
              ? "基于文档内容回答" 
              : "AI 将根据上下文或通用知识回答"}
          </p>
        </div>
      </main>
    </div>
  )
}
