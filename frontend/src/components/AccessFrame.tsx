import type { ReactNode } from 'react'
import { ArrowLeftOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { Brand } from './Brand'
import { LanguageSwitcher } from './LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'

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
  const { t } = useLanguage()
  return (
    <main className="access-page">
      <section className="access-aside">
        <Brand inverse />
        <div className="access-aside__content">
          <span className="eyebrow eyebrow--light">{t('专业陪伴 · 安全沟通')}</span>
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
        <p className="access-aside__foot">{t('平台辅助表达与医患沟通，实际治疗方案由专业医护人员制定')}</p>
      </section>

      <section className="access-main">
        <div className="access-main__topbar">
          <Link to="/" className="text-link">
            <ArrowLeftOutlined /> {t('返回首页')}
          </Link>
          <div className="access-mobile-brand"><Brand /></div>
          <div className="access-main__tools">
            <span className="access-main__help">{t('需要帮助？请联系平台或现场医护负责人')}</span>
            <LanguageSwitcher />
          </div>
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
