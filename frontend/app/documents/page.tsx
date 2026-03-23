"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import { FileText, Upload, Trash2, RefreshCw, ChevronRight, Layers, X, CheckCircle, AlertCircle, Clock } from "lucide-react"
import { api, Document } from "@/lib/api"
import styles from "./page.module.css"

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadDocuments = useCallback(async () => {
    try {
      const result = await api.listDocuments()
      setDocuments(result.documents)
    } catch (error) {
      console.error("Failed to load documents:", error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    setUploading(true)
    setUploadProgress(0)

    for (const file of Array.from(files)) {
      try {
        await api.uploadDocument(file, (progress) => {
          setUploadProgress(progress)
        })
      } catch (error) {
        console.error("Upload failed:", error)
      }
    }

    setUploading(false)
    setUploadProgress(0)
    loadDocuments()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleUpload(e.dataTransfer.files)
  }

  const handleDelete = async (id: string) => {
    setDeleting(id)
    try {
      await api.deleteDocument(id)
      setDocuments(docs => docs.filter(d => d.id !== id))
    } catch (error) {
      console.error("Delete failed:", error)
    } finally {
      setDeleting(null)
    }
  }

  const handleReindex = async (id: string) => {
    try {
      await api.reindexDocument(id)
      loadDocuments()
    } catch (error) {
      console.error("Reindex failed:", error)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ready":
        return <CheckCircle size={14} className={styles.statusReady} />
      case "indexing":
        return <Clock size={14} className={styles.statusIndexing} />
      case "error":
        return <AlertCircle size={14} className={styles.statusError} />
      default:
        return <Clock size={14} className={styles.statusPending} />
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case "ready": return "就绪"
      case "indexing": return "索引中"
      case "error": return "错误"
      default: return "等待中"
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    })
  }

  return (
    <div className={styles.container}>
      {/* Background Effects */}
      <div className={styles.bgGradient} />
      <div className={styles.bgGrid} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.backLink}>
            <ChevronRight size={20} className={styles.backIcon} />
            <span>返回</span>
          </Link>
          <h1 className={styles.title}>文档管理</h1>
          <div className={styles.headerActions}>
            <button 
              className={styles.uploadBtn}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={18} />
              <span>上传文档</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        {/* Upload Area */}
        <div
          className={`${styles.uploadArea} ${dragOver ? styles.uploadAreaDragOver : ""} ${uploading ? styles.uploadAreaUploading : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            multiple
            onChange={(e) => handleUpload(e.target.files)}
            className={styles.fileInput}
          />
          
          {uploading ? (
            <div className={styles.uploadProgress}>
              <div className={styles.progressRing}>
                <svg viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="45" className={styles.progressBg} />
                  <circle 
                    cx="50" cy="50" r="45" 
                    className={styles.progressFill}
                    style={{ strokeDasharray: `${uploadProgress * 2.83} 283` }}
                  />
                </svg>
                <span className={styles.progressText}>{Math.round(uploadProgress)}%</span>
              </div>
              <p className={styles.uploadText}>正在上传...</p>
            </div>
          ) : (
            <>
              <div className={styles.uploadIcon}>
                <Upload size={32} />
              </div>
              <p className={styles.uploadText}>
                拖拽文件到此处，或<span className={styles.uploadLink}>点击上传</span>
              </p>
              <p className={styles.uploadHint}>支持 PDF、DOCX、TXT、Markdown 格式</p>
            </>
          )}
        </div>

        {/* Documents List */}
        <div className={styles.documentsSection}>
          <h2 className={styles.sectionTitle}>
            <FileText size={20} />
            我的文档 ({documents.length})
          </h2>

          {loading ? (
            <div className={styles.loading}>
              <div className={styles.spinner} />
              <p>加载中...</p>
            </div>
          ) : documents.length === 0 ? (
            <div className={styles.empty}>
              <FileText size={48} className={styles.emptyIcon} />
              <p>还没有上传任何文档</p>
              <p className={styles.emptyHint}>上传你的第一个文档开始体验</p>
            </div>
          ) : (
            <div className={styles.documentsList}>
              {documents.map((doc, index) => (
                <div 
                  key={doc.id} 
                  className={styles.documentCard}
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className={styles.docIcon}>
                    <FileText size={24} />
                  </div>
                  <div className={styles.docInfo}>
                    <h3 className={styles.docName}>{doc.name}</h3>
                    <div className={styles.docMeta}>
                      <span className={styles.docMetaItem}>
                        {doc.page_count || "-"} 页
                      </span>
                      <span className={styles.docMetaItem}>
                        {formatFileSize(doc.file_size)}
                      </span>
                      <span className={styles.docMetaItem}>
                        {formatDate(doc.created_at)}
                      </span>
                    </div>
                  </div>
                  <div className={styles.docStatus}>
                    <span className={`${styles.statusBadge} ${styles[`status${doc.index_status}`]}`}>
                      {getStatusIcon(doc.index_status)}
                      {getStatusText(doc.index_status)}
                    </span>
                  </div>
                  <div className={styles.docActions}>
                    {doc.index_tree && (
                      <Link 
                        href={`/index-tree?id=${doc.id}`}
                        className={styles.actionBtn}
                        title="查看索引树"
                      >
                        <Layers size={18} />
                      </Link>
                    )}
                    <Link 
                      href={`/chat?doc=${doc.id}`}
                      className={styles.actionBtn}
                      title="开始对话"
                    >
                      <ChevronRight size={18} />
                    </Link>
                    <button 
                      className={styles.actionBtn}
                      onClick={() => handleReindex(doc.id)}
                      title="重新索引"
                      disabled={doc.index_status === "indexing"}
                    >
                      <RefreshCw size={18} className={doc.index_status === "indexing" ? styles.spinning : ""} />
                    </button>
                    <button 
                      className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
                      onClick={() => handleDelete(doc.id)}
                      disabled={deleting === doc.id}
                      title="删除"
                    >
                      {deleting === doc.id ? (
                        <div className={styles.spinnerSmall} />
                      ) : (
                        <Trash2 size={18} />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
