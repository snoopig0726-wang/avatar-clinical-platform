import type { ReactNode } from 'react'
import { ArrowLeftOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { Brand } from './Brand'

type AccessFrameProps = {
  eyebrow: string
  title: string
  description: string
  children: ReactNode
  asideTitle: string
  asideItems: string[]
}

export function AccessFrame({
  eyebrow,
  title,
  description,
  children,
  asideTitle,
  asideItems,
}: AccessFrameProps) {
  return (
    <main className="access-page">
      <section className="access-aside">
        <Brand inverse />
        <div className="access-aside__content">
          <span className="eyebrow eyebrow--light">受监督研究流程</span>
          <h2>{asideTitle}</h2>
          <ul>
            {asideItems.map((item) => (
              <li key={item}>
                <SafetyCertificateOutlined />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="access-aside__foot">本系统不提供诊断、治疗建议或患者自助医疗服务</p>
      </section>

      <section className="access-main">
        <div className="access-main__topbar">
          <Link to="/" className="text-link">
            <ArrowLeftOutlined /> 返回首页
          </Link>
          <span>需要帮助？请联系研究现场负责人</span>
        </div>
        <div className="access-panel">
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p className="access-panel__description">{description}</p>
          {children}
        </div>
      </section>
    </main>
  )
}

