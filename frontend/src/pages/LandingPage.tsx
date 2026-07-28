import {
  LockOutlined,
  MedicineBoxOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Button } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'

const assurances = [
  {
    icon: <MedicineBoxOutlined />,
    title: '更容易说出你的感受',
    copy: '把难以描述的声音体验转化为可以共同观察的图像，帮助你更清楚地告诉医生自己正在经历什么。',
  },
  {
    icon: <SafetyCertificateOutlined />,
    title: '帮助医生理解治疗线索',
    copy: '医生会结合你的描述与反馈，更准确地理解症状变化，为后续评估和治疗调整提供参考。',
  },
  {
    icon: <LockOutlined />,
    title: '在专业陪伴下安心使用',
    copy: '所有内容都会经过安全检查与医生确认，你可以随时表达不适、提出修改或停止当前过程。',
  },
]

const steps = [
  ['01', '说出你的声音体验', '在医生陪伴下描述声音的特点，以及它对情绪和生活的影响。'],
  ['02', '把感受转化为图像', '系统根据你的描述形成视觉表达，让难以言说的体验变得更容易讨论。'],
  ['03', '和医生一起理解', '你与医生共同查看图像、补充感受，并寻找值得进一步关注的症状线索。'],
  ['04', '支持后续治疗调整', '把你的反馈带回治疗过程，持续观察变化，寻找更适合你的应对方式。'],
]

export function LandingPage() {
  const navigate = useNavigate()
  const { t } = useLanguage()

  return (
    <div className="landing-page">
      <header className="site-header">
        <div className="site-header__inner">
          <Brand />
          <nav className="site-nav" aria-label={t('主要导航')}>
            <a href="#workflow">{t('如何使用')}</a>
            <a href="#safety">{t('如何帮助你')}</a>
            <Button type="text" onClick={() => navigate('/admin/login')}>
              {t('医护管理')}
            </Button>
            <LanguageSwitcher />
          </nav>
        </div>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-glow hero-glow--one" />
          <div className="hero-glow hero-glow--two" />
          <div className="container hero-grid hero-grid--immersive">
            <div className="hero-copy">
              <div className="research-badge">
                <span className="research-badge__dot" />
                {t('专业医护陪伴 · 为幻听困扰者提供表达与治疗支持')}
              </div>
              <h1>
                {t('让你的声音被理解，')}
                <span>{t('让治疗更有方向')}</span>
              </h1>
              <p className="hero-copy__lead">
                {t('我们帮助你把听到的声音转化为可以共同观察的图像，让医生更准确地理解你的感受、症状变化和生活影响，为后续治疗与康复支持提供更多线索。')}
              </p>
              <div className="hero-actions">
                <Button
                  type="primary"
                  size="large"
                  icon={<UserOutlined />}
                  onClick={() => navigate('/patient/invite')}
                >
                  {t('我有邀请码，进入会话')}
                </Button>
                <Button
                  type="primary"
                  size="large"
                  icon={<MedicineBoxOutlined />}
                  onClick={() => navigate('/doctor/login')}
                >
                  {t('医护人员登录')}
                </Button>
              </div>
              <div className="hero-notice">
                <SafetyCertificateOutlined />
                <span>{t('本工具用于辅助表达和医患沟通，不能保证治愈，也不替代医生的诊断与治疗')}</span>
              </div>
            </div>

            <figure
              className="hero-visual hero-photo"
              aria-label={t('声音特征进入受控观测框并形成视觉线索的示意图')}
            >
              <img
                src="/images/home-clinical-avatar-session.png"
                alt={t('声音特征进入受控观测框并形成视觉线索的示意图')}
              />
            </figure>
          </div>
        </section>

        <section className="assurance-section" id="safety">
          <div className="container assurance-grid">
            {assurances.map((item) => (
              <article className="assurance-card" key={item.title}>
                <span className="assurance-card__icon">{item.icon}</span>
                <div>
                  <h3>{t(item.title)}</h3>
                  <p>{t(item.copy)}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="workflow-section" id="workflow">
          <div className="container">
            <div className="section-heading">
              <span className="eyebrow">{t('你的治疗支持过程')}</span>
              <h2>{t('从说清感受到逐步改善')}</h2>
              <p>
                {t('每一次描述、观察和反馈，都是为了帮助你与医生更准确地理解症状，持续寻找更适合你的治疗与应对方向。')}
              </p>
            </div>
            <div className="workflow-grid">
              {steps.map(([number, title, description]) => (
                <article className="workflow-card" key={number}>
                  <span className="workflow-card__number">{number}</span>
                  <h3>{t(title)}</h3>
                  <p>{t(description)}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <Brand compact inverse />
          <p>{t('本平台用于辅助患者表达体验与医患沟通，实际治疗方案由专业医护人员制定。')}</p>
          <div>
            <Link to="/patient/invite">{t('患者进入')}</Link>
            <Link to="/doctor/login">{t('医护登录')}</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
