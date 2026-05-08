"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { Settings, Key, Cpu, Save, Check, AlertCircle, RefreshCw, Zap } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
import styles from "./page.module.css"

type LLMProvider = "openai" | "anthropic" | "ollama" | "openai_compatible"

interface ProviderInfo {
  id: string
  name: string
  description: string
  defaults: Record<string, string>
  fields: string[]
}

interface Preset {
  name: string
  base_url: string
  model: string
}

const PRESETS: Preset[] = [
  { name: "DeepSeek", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { name: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
  { name: "Moonshot", base_url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { name: "通义千问", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-turbo" },
  { name: "硅基流动", base_url: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen2.5-7B-Instruct" },
  { name: "自定义", base_url: "", model: "" },
]

// Fixed model options for OpenAI & Anthropic
const OPENAI_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
const ANTHROPIC_MODELS = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"]

export default function SettingsPage() {
  const [provider, setProvider] = useState<LLMProvider>("ollama")
  const [apiKey, setApiKey] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [model, setModel] = useState("")
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [loading, setLoading] = useState(true)

  // Load settings from backend on mount
  const loadSettings = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/settings`)
      const data = await resp.json()
      const s = data.settings || {}
      setProvider((s.llm_provider as LLMProvider) || "ollama")
      setApiKey(s.llm_api_key || "")
      setBaseUrl(s.llm_base_url || "")
      setModel(s.llm_model || "")
    } catch (e) {
      console.error("Failed to load settings:", e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  // Fetch Ollama models when provider is ollama
  useEffect(() => {
    if (provider === "ollama" && !loading) {
      fetchOllamaModels()
    }
  }, [provider, loading])

  const fetchOllamaModels = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/models`)
      const data = await resp.json()
      if (data.models && data.models.length > 0) {
        setOllamaModels(data.models)
        if (!data.models.includes(model)) {
          setModel(data.models[0])
        }
      }
    } catch (e) {
      console.error("Failed to fetch Ollama models:", e)
    }
  }

  const handleSave = async () => {
    try {
      setSaved(false)
      setError(null)
      const resp = await fetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: {
            llm_provider: provider,
            llm_api_key: apiKey,
            llm_base_url: baseUrl,
            llm_model: model,
          },
        }),
      })
      if (!resp.ok) throw new Error("Save failed")
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError("保存失败，请重试")
    }
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      // Save first
      await fetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          settings: {
            llm_provider: provider,
            llm_api_key: apiKey,
            llm_base_url: baseUrl,
            llm_model: model,
          },
        }),
      })
      const resp = await fetch(`${API_BASE}/api/settings/test`, { method: "POST" })
      const data = await resp.json()
      setTestResult({ ok: data.success, msg: data.message })
      // Refresh Ollama models if applicable
      if (provider === "ollama") {
        fetchOllamaModels()
      }
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) })
    } finally {
      setTesting(false)
    }
  }

  const applyPreset = (preset: Preset) => {
    setBaseUrl(preset.base_url)
    setModel(preset.model)
  }

  const providerCards: { id: LLMProvider; name: string; icon?: string }[] = [
    { id: "openai", name: "OpenAI" },
    { id: "anthropic", name: "Anthropic" },
    { id: "ollama", name: "Ollama (本地)" },
    { id: "openai_compatible", name: "OpenAI 兼容" },
  ]

  if (loading) {
    return (
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.headerContent}>
            <Link href="/" className={styles.backLink}>← 返回</Link>
            <h1 className={styles.title}><Settings size={24} /> 设置</h1>
          </div>
        </header>
        <main className={styles.main}>
          <div className={styles.loading}>加载中...</div>
        </main>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.bgGradient} />
      <div className={styles.bgGrid} />

      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.backLink}>← 返回</Link>
          <h1 className={styles.title}><Settings size={24} /> 设置</h1>
        </div>
      </header>

      <main className={styles.main}>
        {/* LLM Provider Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Cpu size={20} />
            <div>
              <h2>语言模型配置</h2>
              <p>选择并配置您的 LLM 提供商 — 所有配置持久化到数据库，重启不丢失</p>
            </div>
          </div>

          <div className={styles.providerCards}>
            {providerCards.map(p => (
              <div
                key={p.id}
                className={`${styles.providerCard} ${provider === p.id ? styles.providerCardActive : ""}`}
                onClick={() => setProvider(p.id)}
              >
                <div className={styles.providerRadio}>
                  <div className={styles.providerRadioInner} />
                </div>
                <div className={styles.providerInfo}>
                  <h3>{p.name}</h3>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Provider-specific configuration */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Key size={20} />
            <div>
              <h2>连接配置</h2>
              <p>
                {provider === "openai" && "OpenAI 官方 API，需要 API Key"}
                {provider === "anthropic" && "Anthropic 官方 API，需要 API Key"}
                {provider === "ollama" && "本地 Ollama 服务，支持自动获取模型列表"}
                {provider === "openai_compatible" && "任意兼容 OpenAI API 的服务"}
              </p>
            </div>
          </div>

          {/* API Key — for openai, anthropic, openai_compatible */}
          {provider !== "ollama" && (
            <div className={styles.formGroup}>
              <label className={styles.label}>API 密钥</label>
              <input
                type="password"
                className={styles.input}
                placeholder={provider === "openai" ? "sk-..." : provider === "anthropic" ? "sk-ant-..." : "输入 API Key"}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
              />
            </div>
          )}

          {/* Model selector — for openai / anthropic */}
          {(provider === "openai" || provider === "anthropic") && (
            <div className={styles.formGroup}>
              <label className={styles.label}>模型</label>
              <select
                className={styles.input}
                value={model}
                onChange={e => setModel(e.target.value)}
              >
                {(provider === "openai" ? OPENAI_MODELS : ANTHROPIC_MODELS).map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}

          {/* Ollama: URL + model selector + refresh */}
          {provider === "ollama" && (
            <>
              <div className={styles.formGroup}>
                <label className={styles.label}>Ollama 服务地址</label>
                <input
                  type="text"
                  className={styles.input}
                  placeholder="http://localhost:11434/v1"
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>模型</label>
                <div className={styles.modelRow}>
                  <select
                    className={`${styles.input} ${styles.modelSelect}`}
                    value={model}
                    onChange={e => setModel(e.target.value)}
                  >
                    {ollamaModels.length > 0
                      ? ollamaModels.map(m => <option key={m} value={m}>{m}</option>)
                      : <option value="">(点击刷新获取)</option>
                    }
                  </select>
                  <button className={styles.refreshBtn} onClick={fetchOllamaModels} title="刷新模型列表">
                    <RefreshCw size={14} />
                  </button>
                </div>
              </div>
            </>
          )}

          {/* OpenAI compatible: presets + URL + model */}
          {provider === "openai_compatible" && (
            <>
              <div className={styles.formGroup}>
                <label className={styles.label}>
                  <Zap size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
                  快速预设
                </label>
                <div className={styles.presetGrid}>
                  {PRESETS.map(p => (
                    <button
                      key={p.name}
                      className={`${styles.presetBtn} ${baseUrl === p.base_url && model === p.model ? styles.presetBtnActive : ""}`}
                      onClick={() => applyPreset(p)}
                      type="button"
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>Base URL</label>
                <input
                  type="text"
                  className={styles.input}
                  placeholder="https://api.deepseek.com/v1"
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.label}>模型名称</label>
                <input
                  type="text"
                  className={styles.input}
                  placeholder="deepseek-chat"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                />
              </div>
            </>
          )}

          {/* Test connection */}
          <div className={styles.testArea}>
            <button
              className={styles.testBtn}
              onClick={handleTestConnection}
              disabled={testing}
            >
              {testing ? "测试中..." : "🔍 测试连接"}
            </button>
            {testResult && (
              <div className={testResult.ok ? styles.testSuccess : styles.testError}>
                {testResult.ok ? "✅" : "❌"} {testResult.msg}
              </div>
            )}
          </div>
        </section>

        {/* Save */}
        <div className={styles.actions}>
          {error && (
            <div className={styles.error}>
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          {saved && (
            <div className={styles.success}>
              <Check size={16} />
              保存成功（已写入数据库）
            </div>
          )}
          <button className={styles.saveBtn} onClick={handleSave}>
            <Save size={18} />
            保存设置
          </button>
        </div>
      </main>
    </div>
  )
}
