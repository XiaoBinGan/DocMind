"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { Settings, Key, Cpu, Save, Check, AlertCircle, RefreshCw } from "lucide-react"
import styles from "./page.module.css"

type LLMProvider = "openai" | "anthropic" | "local" | "ollama"

interface SettingsState {
  provider: LLMProvider
  openaiKey: string
  openaiModel: string
  anthropicKey: string
  anthropicModel: string
  localUrl: string
  localModel: string
  maxDepth: number
  maxLeafNodes: number
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsState>({
    provider: "ollama",
    openaiKey: "",
    openaiModel: "gpt-4o-mini",
    anthropicKey: "",
    anthropicModel: "claude-3-haiku-20240307",
    localUrl: "http://localhost:11434/v1",
    localModel: "llama3",
    maxDepth: 5,
    maxLeafNodes: 50
  })
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])

  // Load Ollama models on mount or when provider changes
  useEffect(() => {
    if (settings.provider === "ollama") {
      fetchOllamaModels()
    }
  }, [settings.provider])

  const fetchOllamaModels = async () => {
    try {
      const resp = await fetch("http://localhost:8000/api/models")
      const data = await resp.json()
      if (data.models && data.models.length > 0) {
        setOllamaModels(data.models)
        // Auto-select first model if current not in list
        if (!data.models.includes(settings.localModel)) {
          updateSetting("localModel", data.models[0])
        }
      }
    } catch (e) {
      console.error("Failed to fetch Ollama models:", e)
    }
  }

  const handleSave = async () => {
    try {
      localStorage.setItem("docmind-settings", JSON.stringify(settings))
      setSaved(true)
      setError(null)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError("保存失败，请重试")
    }
  }

  const updateSetting = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const resp = await fetch("http://localhost:8000/api/models")
      const data = await resp.json()
      
      if (data.error) {
        setTestResult(`❌ ${data.error}`)
      } else if (data.models && data.models.length > 0) {
        setOllamaModels(data.models)
        setTestResult(`✅ 连接成功！发现 ${data.models.length} 个模型`)
      } else {
        setTestResult(`✅ 已连接到 ${data.base_url || data.provider}`)
      }
    } catch (e) {
      setTestResult(`❌ 连接失败: ${e}`)
    } finally {
      setTesting(false)
    }
  }

  const providerConfigs = [
    { id: "openai" as LLMProvider, name: "OpenAI", models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"] },
    { id: "anthropic" as LLMProvider, name: "Anthropic", models: ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"] },
    { id: "ollama" as LLMProvider, name: "Ollama (本地)", models: ollamaModels.length > 0 ? ollamaModels : ["(点击刷新获取)"] }
  ]

  return (
    <div className={styles.container}>
      {/* Background Effects */}
      <div className={styles.bgGradient} />
      <div className={styles.bgGrid} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link href="/" className={styles.backLink}>
            ← 返回
          </Link>
          <h1 className={styles.title}>
            <Settings size={24} />
            设置
          </h1>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        {/* LLM Provider Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Cpu size={20} />
            <div>
              <h2>语言模型配置</h2>
              <p>选择并配置您的 LLM 提供商</p>
            </div>
          </div>

          <div className={styles.providerCards}>
            {providerConfigs.map(provider => (
              <div
                key={provider.id}
                className={`${styles.providerCard} ${settings.provider === provider.id ? styles.providerCardActive : ""}`}
                onClick={() => updateSetting("provider", provider.id)}
              >
                <div className={styles.providerRadio}>
                  <div className={styles.providerRadioInner} />
                </div>
                <div className={styles.providerInfo}>
                  <h3>{provider.name}</h3>
                  {settings.provider === provider.id && (
                    <div className={styles.modelSelectRow}>
                      <select
                        className={styles.modelSelect}
                        value={settings.provider === "ollama" ? settings.localModel : (settings as any)[`${provider.id}Model`] || ""}
                        onChange={(e) => {
                          if (provider.id === "ollama") {
                            updateSetting("localModel", e.target.value)
                          } else {
                            updateSetting(`${provider.id}Model` as any, e.target.value)
                          }
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {provider.models.map(m => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                      {provider.id === "ollama" && (
                        <button
                          className={styles.refreshBtn}
                          onClick={(e) => { e.stopPropagation(); fetchOllamaModels() }}
                          title="刷新模型列表"
                        >
                          <RefreshCw size={14} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* API Keys Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Key size={20} />
            <div>
              <h2>API 密钥 / 连接</h2>
              <p>配置 API 密钥或本地服务地址</p>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>OpenAI API Key</label>
            <input
              type="password"
              className={styles.input}
              placeholder="sk-..."
              value={settings.openaiKey}
              onChange={(e) => updateSetting("openaiKey", e.target.value)}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Anthropic API Key</label>
            <input
              type="password"
              className={styles.input}
              placeholder="sk-ant-..."
              value={settings.anthropicKey}
              onChange={(e) => updateSetting("anthropicKey", e.target.value)}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.label}>Ollama / 本地模型 URL</label>
            <input
              type="text"
              className={styles.input}
              placeholder="http://localhost:11434/v1"
              value={settings.localUrl}
              onChange={(e) => updateSetting("localUrl", e.target.value)}
            />
            <div className={styles.inputActions}>
              <button 
                className={styles.testBtn}
                onClick={handleTestConnection}
                disabled={testing}
              >
                {testing ? "连接中..." : "🔍 测试连接"}
              </button>
              {testResult && (
                <span className={styles.testResult}>{testResult}</span>
              )}
            </div>
          </div>
        </section>

        {/* PageIndex Settings Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Settings size={20} />
            <div>
              <h2>索引参数</h2>
              <p>配置 PageIndex 索引行为</p>
            </div>
          </div>

          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className={styles.label}>最大树深度</label>
              <input
                type="number"
                className={styles.input}
                min={1}
                max={10}
                value={settings.maxDepth}
                onChange={(e) => updateSetting("maxDepth", parseInt(e.target.value) || 5)}
              />
              <span className={styles.hint}>索引树的最大层级数</span>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>最大叶子节点数</label>
              <input
                type="number"
                className={styles.input}
                min={10}
                max={200}
                value={settings.maxLeafNodes}
                onChange={(e) => updateSetting("maxLeafNodes", parseInt(e.target.value) || 50)}
              />
              <span className={styles.hint}>每个分支的最大节点数</span>
            </div>
          </div>
        </section>

        {/* Save Button */}
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
              保存成功
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