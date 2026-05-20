"use client"

import { useState, useEffect, useCallback } from "react"
import { apiCatalog, chains, type ApiDefinition, type SerialChain, type ChainMember } from "@/lib/api"
import styles from "./page.module.css"

type Tab = "apis" | "chains"

export default function ApiCatalogPage() {
  const [tab, setTab] = useState<Tab>("apis")
  const [apis, setApis] = useState<ApiDefinition[]>([])
  const [chainList, setChainList] = useState<SerialChain[]>([])
  const [loading, setLoading] = useState(true)

  // Modal state
  const [showApiModal, setShowApiModal] = useState(false)
  const [showChainModal, setShowChainModal] = useState(false)
  const [editingApi, setEditingApi] = useState<ApiDefinition | null>(null)
  const [editingChain, setEditingChain] = useState<SerialChain | null>(null)

  useEffect(() => {
    Promise.all([
      apiCatalog.list().then(setApis).catch(() => setApis([])),
      chains.list().then(setChainList).catch(() => setChainList([])),
    ]).finally(() => setLoading(false))
  }, [])

  const reload = useCallback(() => {
    Promise.all([
      apiCatalog.list().then(setApis).catch(() => {}),
      chains.list().then(setChainList).catch(() => {}),
    ])
  }, [])

  const toggleApi = async (id: string, enabled: boolean) => {
    try {
      const updated = await apiCatalog.toggle(id, enabled)
      setApis(prev => prev.map(a => a.id === id ? updated : a))
    } catch {}
  }

  const deleteApi = async (id: string) => {
    if (!confirm("确定删除此 API？")) return
    try {
      await apiCatalog.delete(id)
      setApis(prev => prev.filter(a => a.id !== id))
    } catch {}
  }

  const deleteChain = async (id: string) => {
    if (!confirm("确定删除此链？")) return
    try {
      await chains.delete(id)
      setChainList(prev => prev.filter(c => c.id !== id))
    } catch {}
  }

  const methodBadge = (method: string) => {
    const cls: Record<string, string> = {
      GET: styles.badgeGet, POST: styles.badgePost,
      PUT: styles.badgePut, DELETE: styles.badgeDelete, PATCH: styles.badgePut,
    }
    return <span className={`${styles.badge} ${cls[method] || styles.badgePost}`}>{method}</span>
  }

  if (loading) {
    return <div className={styles.container}><div className={styles.pageInner}><div className={styles.emptyState}>加载中...</div></div></div>
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageInner}>
        {/* Header */}
        <div className={styles.header}>
          <h1 className={styles.title}>📡 API 目录</h1>
        </div>

        {/* Tabs */}
        <div className={styles.tabBar}>
          <button className={`${styles.tab} ${tab === "apis" ? styles.tabActive : ""}`} onClick={() => setTab("apis")}>
            API Catalog
          </button>
          <button className={`${styles.tab} ${tab === "chains" ? styles.tabActive : ""}`} onClick={() => setTab("chains")}>
            串行链
          </button>
        </div>

        {/* API Catalog Tab */}
        {tab === "apis" && (
          <div>
            <div style={{ marginBottom: 16, display: "flex", gap: 8 }}>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => { setEditingApi(null); setShowApiModal(true) }}>
                + 新增 API
              </button>
            </div>
            <div className={styles.cardList}>
              {apis.length === 0 && <div className={styles.emptyState}>暂无 API，点击上方按钮添加</div>}
              {apis.map(api => (
                <div key={api.id} className={styles.card}>
                  <div className={styles.cardHeader}>
                    <h3 className={styles.cardName}>{api.name}</h3>
                    <button className={styles.btn} style={{ fontSize: "11px" }} onClick={() => { setEditingApi(api); setShowApiModal(true) }}>
                      编辑
                    </button>
                  </div>
                  <p className={styles.cardDesc}>{api.description || "暂无描述"}</p>
                  <div className={styles.cardMeta}>
                    {methodBadge(api.method)}
                    <span>{api.base_url}{api.path}</span>
                    <span className={api.enabled ? styles.badgeEnabled : styles.badgeDisabled}>
                      {api.enabled ? "启用" : "禁用"}
                    </span>
                  </div>
                  <div className={styles.cardActions}>
                    <button className={styles.btn} style={{ fontSize: "11px" }} onClick={() => toggleApi(api.id, !api.enabled)}>
                      {api.enabled ? "禁用" : "启用"}
                    </button>
                    <button className={`${styles.btn} ${styles.btnDanger}`} style={{ fontSize: "11px" }} onClick={() => deleteApi(api.id)}>
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chains Tab */}
        {tab === "chains" && (
          <div>
            <div style={{ marginBottom: 16, display: "flex", gap: 8 }}>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={() => { setEditingChain(null); setShowChainModal(true) }}>
                + 新增链
              </button>
            </div>
            <div className={styles.cardList}>
              {chainList.length === 0 && <div className={styles.emptyState}>暂无链，点击上方按钮添加</div>}
              {chainList.map(chain => (
                <div key={chain.id} className={styles.chainCard}>
                  <div className={styles.chainHeader}>
                    <h3 className={styles.chainName}>{chain.name}</h3>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button className={styles.btn} style={{ fontSize: "11px" }} onClick={() => { setEditingChain(chain); setShowChainModal(true) }}>
                        编辑
                      </button>
                      <button className={`${styles.btn} ${styles.btnDanger}`} style={{ fontSize: "11px" }} onClick={() => deleteChain(chain.id)}>
                        删除
                      </button>
                    </div>
                  </div>
                  <p className={styles.chainDesc}>{chain.description || "暂无描述"}</p>
                  <div className={styles.chainSteps}>
                    {chain.steps_count} 步
                    <span className={chain.enabled ? styles.badgeEnabled : styles.badgeDisabled}>
                      {chain.enabled ? "启用" : "禁用"}
                    </span>
                  </div>
                  {chain.members.length > 0 && (
                    <div className={styles.stepList}>
                      {chain.members.map(m => (
                        <div key={m.id} className={styles.stepItem}>
                          <span className={styles.stepNum}>{m.order}</span>
                          <span>{m.api_name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* API Modal */}
        {showApiModal && (
          <ApiModal
            api={editingApi}
            onClose={() => setShowApiModal(false)}
            onSave={reload}
          />
        )}

        {/* Chain Modal */}
        {showChainModal && (
          <ChainModal
            chain={editingChain}
            apis={apis}
            onClose={() => setShowChainModal(false)}
            onSave={reload}
          />
        )}
      </div>
    </div>
  )
}

// ── Inline API Modal ──
function ApiModal({ api, onClose, onSave }: { api: ApiDefinition | null; onClose: () => void; onSave: () => void }) {
  const [name, setName] = useState(api?.name || "")
  const [desc, setDesc] = useState(api?.description || "")
  const [baseUrl, setBaseUrl] = useState(api?.base_url || "")
  const [method, setMethod] = useState(api?.method || "GET")
  const [path, setPath] = useState(api?.path || "/")
  const [headers, setHeaders] = useState(JSON.stringify(api?.headers || {}, null, 2))
  const [bodySchema, setBodySchema] = useState(JSON.stringify(api?.body_schema || {}, null, 2))
  const [authType, setAuthType] = useState(api?.auth_type || "none")

  const handleSave = async () => {
    try {
      const data = {
        name, description: desc, base_url: baseUrl, method, path,
        headers: headers ? JSON.parse(headers) : {},
        body_schema: bodySchema ? JSON.parse(bodySchema) : {},
        auth_type: authType, auth_header: "",
      }
      if (api) {
        await apiCatalog.update(api.id, data)
      } else {
        await apiCatalog.create(data)
      }
      onSave()
      onClose()
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败")
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h2 className={styles.modalTitle}>{api ? "编辑 API" : "新增 API"}</h2>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>名称</label>
          <input className={styles.formInput} value={name} onChange={e => setName(e.target.value)} placeholder="API 名称" />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>描述</label>
          <input className={styles.formInput} value={desc} onChange={e => setDesc(e.target.value)} placeholder="描述" />
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>方法</label>
            <select className={styles.formInput} value={method} onChange={e => setMethod(e.target.value)}>
              {["GET", "POST", "PUT", "DELETE", "PATCH"].map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>路径</label>
            <input className={styles.formInput} value={path} onChange={e => setPath(e.target.value)} placeholder="/" />
          </div>
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Base URL</label>
          <input className={styles.formInput} value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.example.com" />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Headers (JSON)</label>
          <textarea className={styles.formTextarea} value={headers} onChange={e => setHeaders(e.target.value)} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>Body Schema (JSON)</label>
          <textarea className={styles.formTextarea} value={bodySchema} onChange={e => setBodySchema(e.target.value)} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>认证类型</label>
          <select className={styles.formInput} value={authType} onChange={e => setAuthType(e.target.value)}>
            {["none", "bearer", "basic", "api_key"].map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div className={styles.modalActions}>
          <button className={styles.btn} onClick={onClose}>取消</button>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSave}>保存</button>
        </div>
      </div>
    </div>
  )
}

// ── Inline Chain Modal ──
function ChainModal({ chain, apis, onClose, onSave }: { chain: SerialChain | null; apis: ApiDefinition[]; onClose: () => void; onSave: () => void }) {
  const [name, setName] = useState(chain?.name || "")
  const [desc, setDesc] = useState(chain?.description || "")
  const [members, setMembers] = useState<{ order: number; api_id: string }[]>(
    chain?.members.map(m => ({ order: m.order, api_id: m.api_id })) || [{ order: 1, api_id: "" }]
  )

  const addMember = () => setMembers([...members, { order: members.length + 1, api_id: "" }])
  const removeMember = (i: number) => setMembers(members.filter((_, idx) => idx !== i).map((m, idx) => ({ ...m, order: idx + 1 })))

  const handleSave = async () => {
    try {
      const data = {
        name, description: desc,
        members: members.map((m, idx) => ({
          order: idx + 1,
          api_id: m.api_id,
          input_mapping: {},
          output_mapping: {},
        })),
      }
      if (chain) {
        await chains.update(chain.id, data)
      } else {
        await chains.create(data)
      }
      onSave()
      onClose()
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败")
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <h2 className={styles.modalTitle}>{chain ? "编辑链" : "新增链"}</h2>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>名称</label>
          <input className={styles.formInput} value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>描述</label>
          <input className={styles.formInput} value={desc} onChange={e => setDesc(e.target.value)} />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>步骤</label>
          {members.map((m, i) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
              <span style={{ width: 20, textAlign: "center", color: "var(--accent-primary)", fontWeight: 600 }}>{i + 1}</span>
              <select className={styles.formInput} style={{ flex: 1 }} value={m.api_id}
                onChange={e => { const n = [...members]; n[i] = { ...n[i], api_id: e.target.value }; setMembers(n); }}>
                <option value="">选择 API</option>
                {apis.filter(a => a.enabled).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              {members.length > 1 && (
                <button className={styles.btn} style={{ padding: "4px 8px" }} onClick={() => removeMember(i)}>✕</button>
              )}
            </div>
          ))}
          <button className={styles.btn} onClick={addMember} style={{ marginTop: 4, fontSize: "12px" }}>+ 添加步骤</button>
        </div>
        <div className={styles.modalActions}>
          <button className={styles.btn} onClick={onClose}>取消</button>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSave}>保存</button>
        </div>
      </div>
    </div>
  )
}
