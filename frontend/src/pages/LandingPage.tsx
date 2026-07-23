import {
  ArrowRightOutlined,
  AuditOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  LockOutlined,
  MedicineBoxOutlined,
  SafetyCertificateOutlined,
  SoundOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Button } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'

const assurances = [
  {
    icon: <MedicineBoxOutlined />,
    title: '医生全程监督',
    copy: '访谈、生成、审核与患者展示均由当前监督医生控制。',
  },
  {
    icon: <SafetyCertificateOutlined />,
    title: '多重安全门禁',
    copy: '图片安全检查与医生人工审核相互独立，任何失败均保留原版本。',
  },
  {
    icon: <LockOutlined />,
    title: '数据最小化',
    copy: '患者不注册、不建立长期账户，病例归档后按期永久删除。',
  },
]

const steps = [
  ['01', '结构化访谈', '医生当面询问并录入 Q1-Q8'],
  ['02', '视觉特征确认', '检查映射结果并进行受控调整'],
  ['03', '生成与安全审核', '候选图片经过系统与人工双重审核'],
  ['04', '受控共同查看', '仅向当前会话展示已授权版本'],
]

export function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="landing-page">
      <header className="site-header">
        <div className="site-header__inner">
          <Brand />
          <nav className="site-nav" aria-label="主要导航">
            <a href="#workflow">研究流程</a>
            <a href="#safety">安全边界</a>
            <Button type="text" onClick={() => navigate('/admin/login')}>
              管理员
            </Button>
          </nav>
        </div>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-glow hero-glow--one" />
          <div className="hero-glow hero-glow--two" />
          <div className="container hero-grid">
            <div className="hero-copy">
              <div className="research-badge">
                <span className="research-badge__dot" />
                临床研究内部原型 · 医生监督使用
              </div>
              <h1>
                将难以言说的声音体验，
                <span>转化为可共同观察的视觉线索</span>
              </h1>
              <p className="hero-copy__lead">
                通过结构化访谈、受控视觉映射和多重审核门禁，帮助医生与患者在安全边界内共同观察幻听声音体验。
              </p>
              <div className="hero-actions">
                <Button
                  type="primary"
                  size="large"
                  icon={<MedicineBoxOutlined />}
                  onClick={() => navigate('/doctor/login')}
                >
                  医生进入工作台
                </Button>
                <Button
                  size="large"
                  icon={<UserOutlined />}
                  onClick={() => navigate('/patient/invite')}
                >
                  输入邀请码进入会话
                </Button>
              </div>
              <div className="hero-notice">
                <SafetyCertificateOutlined />
                <span>非诊断、非真实身份复刻，不替代专业照护与临床判断</span>
              </div>
            </div>

            <div className="hero-visual" aria-label="声音特征进入受控观测框并形成视觉线索的示意图">
              <div className="observation-card">
                <div className="observation-card__head">
                  <div>
                    <span className="observation-label">受控观测</span>
                    <strong>当前候选视觉表达</strong>
                  </div>
                  <span className="secure-pill">
                    <LockOutlined /> 医生可见
                  </span>
                </div>

                <div className="portrait-stage">
                  <div className="sound-orbit sound-orbit--one" />
                  <div className="sound-orbit sound-orbit--two" />
                  <div className="portrait-halo" />
                  <div className="portrait-figure">
                    <div className="portrait-figure__hair" />
                    <div className="portrait-figure__face">
                      <i className="portrait-eye portrait-eye--left" />
                      <i className="portrait-eye portrait-eye--right" />
                      <i className="portrait-nose" />
                      <i className="portrait-mouth" />
                    </div>
                    <div className="portrait-figure__shoulders" />
                  </div>
                  <div className="waveform" aria-hidden="true">
                    {[12, 25, 42, 24, 55, 31, 64, 34, 48, 20, 39, 16].map((height, index) => (
                      <i key={`${height}-${index}`} style={{ height }} />
                    ))}
                  </div>
                </div>

                <div className="observation-card__foot">
                  <span>
                    <CheckCircleFilled /> 结构化特征已确认
                  </span>
                  <span>
                    <ClockCircleOutlined /> 等待生成
                  </span>
                </div>
              </div>
              <div className="floating-note floating-note--top">
                <SoundOutlined />
                <span>
                  <small>声音特征</small>
                  八项结构化维度
                </span>
              </div>
              <div className="floating-note floating-note--bottom">
                <AuditOutlined />
                <span>
                  <small>审核门禁</small>
                  未授权内容患者不可见
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="assurance-section" id="safety">
          <div className="container assurance-grid">
            {assurances.map((item) => (
              <article className="assurance-card" key={item.title}>
                <span className="assurance-card__icon">{item.icon}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="workflow-section" id="workflow">
          <div className="container">
            <div className="section-heading">
              <span className="eyebrow">受监督研究流程</span>
              <h2>每一步都有清晰边界</h2>
              <p>模型只负责受控生成，业务状态、安全判断和患者展示始终由系统与医生共同把关。</p>
            </div>
            <div className="workflow-grid">
              {steps.map(([number, title, description], index) => (
                <article className="workflow-card" key={number}>
                  <span className="workflow-card__number">{number}</span>
                  <h3>{title}</h3>
                  <p>{description}</p>
                  {index < steps.length - 1 && <ArrowRightOutlined className="workflow-card__arrow" />}
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <Brand compact inverse />
          <p>本平台仅用于医生监督下的研究辅助，不提供诊断或治疗建议。</p>
          <div>
            <Link to="/doctor/login">医生登录</Link>
            <Link to="/patient/invite">受邀患者</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

