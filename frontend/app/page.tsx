"use client"

import { useState } from "react"
import Link from "next/link"
import { FileText, MessageSquare, Settings, Sparkles, ChevronRight, Layers, Github } from "lucide-react"
import styles from "./page.module.css"

export default function Home() {
  const [hoveredCard, setHoveredCard] = useState<number | null>(null)

  const features = [
    {
      icon: <Layers className={styles.featureIcon} />,
      title: "智能索引",
      description: "像专家一样阅读文档",
      link: "/documents"
    },
    {
      icon: <MessageSquare className={styles.featureIcon} />,
      title: "智能问答",
      description: "基于文档内容的精准回答",
      link: "/chat"
    },
    {
      icon: <Sparkles className={styles.featureIcon} />,
      title: "无向量检索",
      description: "告别向量相似度，拥抱真正相关性",
      link: "/documents"
    }
  ]

  return (
    <div className={styles.container}>
      {/* Background Effects */}
      <div className={styles.bgGradient} />
      <div className={styles.bgGrid} />
      <div className={styles.bgGlow1} />
      <div className={styles.bgGlow2} />

      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={styles.navContent}>
          <div className={styles.logo}>
            <div className={styles.logoIcon}>
              <Layers size={24} />
            </div>
            <span className={styles.logoText}>DocMind</span>
          </div>
          <div className={styles.navLinks}>
            <Link href="/documents" className={styles.navLink}>
              <FileText size={18} />
              文档
            </Link>
            <Link href="/chat" className={styles.navLink}>
              <MessageSquare size={18} />
              对话
            </Link>
            <Link href="/settings" className={styles.navLink}>
              <Settings size={18} />
              设置
            </Link>
            <a
              href="https://github.com/XiaoBinGan/DocMind"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.navLink}
            >
              <Github size={18} />
              GitHub
            </a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className={styles.main}>
        <div className={styles.hero}>
          <div className={styles.heroBadge}>
            <Sparkles size={14} />
            <span>推理式文档问答</span>
          </div>
          
          <h1 className={styles.heroTitle}>
            让 AI 像
            <span className={styles.heroHighlight}>专家</span>
            一样阅读文档
          </h1>
          
          <p className={styles.heroSubtitle}>
            告别传统向量检索的局限性。<br />
            DocMind 模拟人类专家的阅读方式，<br />
            通过推理找到真正相关的内容。
          </p>

          <div className={styles.heroCta}>
            <Link href="/documents" className={styles.ctaPrimary}>
              开始使用
              <ChevronRight size={20} />
            </Link>
            <Link href="/chat" className={styles.ctaSecondary}>
              体验对话
            </Link>
          </div>
        </div>

        {/* Features Grid */}
        <div className={styles.features}>
          {features.map((feature, index) => (
            <Link
              key={index}
              href={feature.link}
              className={`${styles.featureCard} ${hoveredCard === index ? styles.featureCardHover : ""}`}
              onMouseEnter={() => setHoveredCard(index)}
              onMouseLeave={() => setHoveredCard(null)}
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className={styles.featureIconWrapper}>
                {feature.icon}
              </div>
              <h3 className={styles.featureTitle}>{feature.title}</h3>
              <p className={styles.featureDesc}>{feature.description}</p>
              <ChevronRight className={styles.featureArrow} size={20} />
            </Link>
          ))}
        </div>

        {/* How it works */}
        <div className={styles.howItWorks}>
          <h2 className={styles.sectionTitle}>工作原理</h2>
          <div className={styles.steps}>
            <div className={styles.step}>
              <div className={styles.stepNumber}>1</div>
              <div className={styles.stepContent}>
                <h3>上传文档</h3>
                <p>支持 PDF、DOCX、TXT 等格式</p>
              </div>
            </div>
            <div className={styles.stepConnector} />
            <div className={styles.step}>
              <div className={styles.stepNumber}>2</div>
              <div className={styles.stepContent}>
                <h3>构建索引树</h3>
                <p>智能分析文档结构</p>
              </div>
            </div>
            <div className={styles.stepConnector} />
            <div className={styles.step}>
              <div className={styles.stepNumber}>3</div>
              <div className={styles.stepContent}>
                <h3>推理问答</h3>
                <p>AI 遍历索引树，找到真正答案</p>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className={styles.footer}>
        <p>DocMind - Powered by LLM</p>
        <a
          href="https://github.com/XiaoBinGan/DocMind"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.footerGithub}
        >
          <Github size={16} />
          XiaoBinGan/DocMind
        </a>
      </footer>
    </div>
  )
}
