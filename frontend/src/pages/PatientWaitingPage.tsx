import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FormOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Alert, Button, Input, Modal, Progress, Spin, Tag } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  clearPatientSession,
  getPatientSessionToken,
  newIdempotencyKey,
  type AdjustmentStatus,
  type PatientAdjustmentList,
  type PatientAvatar,
  type PatientSession,
  type SubmitAdjustmentResponse,
} from '../lib/api'

const sessionCopy: Record<PatientSession['status'], { eyebrow: string; title: string; copy: string }> = {
  waiting_doctor: {
    eyebrow: '已经安全进入',
    title: '医生正在为你准备',
    copy: '你不需要进行任何操作，请和医生一起留在当前页面。准备完成后，这里会自动更新。',
  },
  active: {
    eyebrow: '医生已确认',
    title: '一起看看它是否接近你的感受',
    copy: '这张图像用来帮助你表达声音体验。你可以告诉医生哪些地方接近、哪些地方需要调整。',
  },
  paused: {
    eyebrow: '已经为你暂停',
    title: '先停下来休息一下',
    copy: '页面内容和后续操作都已停止。请把你的感受告诉身边的医生，准备好后再由医生恢复。',
  },
  ended: {
    eyebrow: '会话已结束',
    title: '会话已结束，感谢您的参与及配合！',
    copy: '谢谢你的参与。接下来可以继续和医生讨论感受；如需再次进入，医生会提供新的邀请码。',
  },
  expired: {
    eyebrow: '会话已过期',
    title: '请让医生提供新的邀请码',
    copy: '当前邀请码已失效，你的数据不会因此丢失。请直接告诉身边的医生。',
  },
}

const adjustmentLabels: Record<AdjustmentStatus, { label: string; color: string }> = {
  pending_doctor_review: { label: '等待医生审核', color: 'processing' },
  approved_as_is: { label: '医生已接受', color: 'blue' },
  approved_edited: { label: '医生调整后接受', color: 'blue' },
  rejected: { label: '医生未采纳', color: 'default' },
  generating: { label: '正在处理', color: 'processing' },
  applied: { label: '已更新', color: 'success' },
  generation_failed: { label: '本次处理未完成', color: 'warning' },
  cancelled: { label: '已取消', color: 'default' },
}

export function PatientWaitingPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const [pauseOpen, setPauseOpen] = useState(false)
  const [endedNoticeOpen, setEndedNoticeOpen] = useState(false)
  const [session, setSession] = useState<PatientSession | null>(null)
  const [avatar, setAvatar] = useState<PatientAvatar | null>(null)
  const [adjustments, setAdjustments] = useState<PatientAdjustmentList | null>(null)
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(true)
  const [pausing, setPausing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [adjustmentError, setAdjustmentError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [feedbackMode, setFeedbackMode] = useState<'choice' | 'adjust' | 'satisfied'>(
    'choice',
  )
  const endedNoticeShown = useRef(false)
  const terminalSessionReached = useRef(false)
  const sessionRefreshRunning = useRef(false)

  const patientToken = useCallback(() => {
    if (!sessionId) return null
    return getPatientSessionToken(sessionId)
  }, [sessionId])

  const loadAuthorizedContent = useCallback(async () => {
    const token = patientToken()
    if (!token || !sessionId) return
    try {
      const [avatarResult, adjustmentResult] = await Promise.all([
        apiRequest<PatientAvatar>(`/patient-sessions/${sessionId}/avatar`, {
          patientToken: token,
        }),
        apiRequest<PatientAdjustmentList>(
          `/patient-sessions/${sessionId}/adjustment-requests`,
          { patientToken: token },
        ),
      ])
      setAvatar(avatarResult)
      setAdjustments(adjustmentResult)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.code === 'STATE_CONFLICT') {
        setAvatar(null)
        return
      }
      setError(requestError instanceof Error ? requestError.message : t('授权内容暂时无法加载'))
    }
  }, [patientToken, sessionId])

  const loadSession = useCallback(async () => {
    if (!sessionId) return
    const token = patientToken()
    if (!token) {
      navigate('/patient/invite', { replace: true })
      return
    }
    try {
      const result = await apiRequest<PatientSession>(`/sessions/${sessionId}`, {
        patientToken: token,
      })
      setSession(result)
      setError(null)
      if (result.status === 'ended' && !endedNoticeShown.current) {
        terminalSessionReached.current = true
        endedNoticeShown.current = true
        setAvatar(null)
        setAdjustments(null)
        setPauseOpen(false)
        setEndedNoticeOpen(true)
      }
      if (result.status === 'expired') terminalSessionReached.current = true
      if (result.status === 'active') await loadAuthorizedContent()
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError
          ? requestError.message
          : t('暂时无法同步会话状态，请保持当前页面'),
      )
    } finally {
      setLoading(false)
    }
  }, [loadAuthorizedContent, navigate, patientToken, sessionId])

  useEffect(() => {
    const refreshVisibleSession = async () => {
      if (
        document.visibilityState !== 'visible' ||
        sessionRefreshRunning.current ||
        terminalSessionReached.current
      ) return
      sessionRefreshRunning.current = true
      try {
        await loadSession()
      } finally {
        sessionRefreshRunning.current = false
      }
    }
    void refreshVisibleSession()
    const timer = window.setInterval(() => void refreshVisibleSession(), 2000)
    window.addEventListener('focus', refreshVisibleSession)
    document.addEventListener('visibilitychange', refreshVisibleSession)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refreshVisibleSession)
      document.removeEventListener('visibilitychange', refreshVisibleSession)
    }
  }, [loadSession])

  const feedbackStorageKey =
    sessionId && avatar?.version_id
      ? `patient-avatar-feedback:${sessionId}:${avatar.version_id}`
      : null

  useEffect(() => {
    if (!feedbackStorageKey) return
    if (adjustments?.has_pending) {
      setFeedbackMode('adjust')
      return
    }
    if (session?.patient_satisfied_version_id === avatar?.version_id) {
      setFeedbackMode('satisfied')
      window.sessionStorage.setItem(feedbackStorageKey, 'satisfied')
      return
    }
    const savedMode = window.sessionStorage.getItem(feedbackStorageKey)
    if (savedMode === 'satisfied') {
      window.sessionStorage.removeItem(feedbackStorageKey)
      setFeedbackMode('choice')
      return
    }
    setFeedbackMode(
      savedMode === 'adjust' ? savedMode : 'choice',
    )
  }, [
    adjustments?.has_pending,
    avatar?.version_id,
    feedbackStorageKey,
    session?.patient_satisfied_version_id,
  ])

  async function chooseFeedbackMode(mode: 'choice' | 'adjust' | 'satisfied') {
    setAdjustmentError(null)
    setSuccess(null)
    const shouldSyncSatisfaction =
      mode === 'satisfied' || feedbackMode === 'satisfied'
    if (shouldSyncSatisfaction) {
      const token = patientToken()
      if (!sessionId || !token || !avatar?.version_id) return
      setFeedbackSubmitting(true)
      try {
        const result = await apiRequest<PatientSession>(
          `/patient-sessions/${sessionId}/avatar-feedback`,
          {
            method: 'POST',
            patientToken: token,
            idempotencyKey: newIdempotencyKey('patient-avatar-feedback'),
            body: {
              version_id: avatar.version_id,
              satisfied: mode === 'satisfied',
            },
          },
        )
        setSession(result)
      } catch (requestError) {
        setAdjustmentError(
          requestError instanceof ApiClientError
            ? requestError.message
            : t('满意状态暂时无法同步，请稍后重试'),
        )
        return
      } finally {
        setFeedbackSubmitting(false)
      }
    }

    setFeedbackMode(mode)
    if (!feedbackStorageKey) return
    if (mode === 'choice') {
      window.sessionStorage.removeItem(feedbackStorageKey)
    } else {
      window.sessionStorage.setItem(feedbackStorageKey, mode)
    }
  }

  async function pauseSession() {
    const token = patientToken()
    if (!sessionId || !token) return
    setPausing(true)
    try {
      const result = await apiRequest<PatientSession>(`/patient-sessions/${sessionId}/pause`, {
        method: 'POST',
        patientToken: token,
        idempotencyKey: newIdempotencyKey('safety-pause'),
        body: { reason: 'patient_requested' },
      })
      setSession(result)
      setAvatar(null)
      setPauseOpen(false)
    } catch (requestError) {
      setError(requestError instanceof ApiClientError ? requestError.message : t('暂停请求未能完成'))
    } finally {
      setPausing(false)
    }
  }

  function leaveEndedSession() {
    setEndedNoticeOpen(false)
    if (sessionId) {
      clearPatientSession(sessionId)
      const feedbackPrefix = `patient-avatar-feedback:${sessionId}:`
      for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
        const key = window.sessionStorage.key(index)
        if (key?.startsWith(feedbackPrefix)) {
          window.sessionStorage.removeItem(key)
        }
      }
    }
    navigate('/patient/invite', { replace: true })
  }

  async function submitAdjustment() {
    const token = patientToken()
    if (!sessionId || !token || instruction.trim().length < 2) return
    setSubmitting(true)
    setAdjustmentError(null)
    setSuccess(null)
    try {
      const result = await apiRequest<SubmitAdjustmentResponse>(
        `/patient-sessions/${sessionId}/adjustment-requests`,
        {
          method: 'POST',
          patientToken: token,
          idempotencyKey: newIdempotencyKey('patient-adjustment'),
          body: { instruction: instruction.trim() },
        },
      )
      setInstruction('')
      setSuccess(result.patient_message)
      await loadAuthorizedContent()
    } catch (requestError) {
      setAdjustmentError(
        requestError instanceof ApiClientError ? requestError.message : t('调整建议未能提交，请稍后重试'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const baseCopy = sessionCopy[session?.status ?? 'waiting_doctor']
  const copy =
    session?.status === 'active' && session.assessment_mode === 'reuse_previous'
      ? {
          eyebrow: '沿用上次记录',
          title: '继续上次的治疗会话',
          copy: '医生已沿用你上次完成的描述和视觉方向。你们可以直接继续查看、讨论和补充这次的感受。',
        }
      : baseCopy
  const activeAuthorized = session?.status === 'active' && avatar
  const reusingPrevious =
    session?.status === 'active' && session.assessment_mode === 'reuse_previous'

  return (
    <main className="patient-session-page">
      <header className="patient-session-header">
        <Brand compact />
        <div className="patient-session-header__actions">
          <span><LockOutlined /> {t('当前设备 · 安全陪伴会话')}</span>
          <LanguageSwitcher />
        </div>
      </header>

      {loading ? (
        <section className="waiting-panel"><Spin size="large" tip={t('正在安全连接会话…')} /></section>
      ) : activeAuthorized ? (
        <section className="patient-avatar-workspace">
          <div className="patient-avatar-stage">
            <div className="patient-avatar-stage__heading">
              <div>
                <span className="eyebrow">{t(copy.eyebrow)}</span>
                <h1>{t(copy.title)}</h1>
              </div>
              <Tag color="success" icon={<SafetyCertificateOutlined />}>{t('医生已确认，可安心查看')}</Tag>
            </div>
            {avatar.display_mode === 'image' && avatar.image_url ? (
              <div className="patient-avatar-portrait patient-avatar-portrait--image">
                <img src={avatar.image_url} alt={t('医生已审核授权的 Avatar')} />
              </div>
            ) : (
              <div className="patient-avatar-portrait" aria-label={t('Avatar 图像暂不可用')}>
                <span className="patient-avatar-portrait__halo" />
                <UserOutlined />
                <span className="patient-avatar-portrait__caption">{t('图像正在准备')}</span>
              </div>
            )}
            <p className="patient-avatar-stage__copy">{t(copy.copy)}</p>
            {avatar.message && <Alert type="info" showIcon message={avatar.message} />}
          </div>

          <aside className="patient-adjustment-panel">
            {feedbackMode === 'choice' ? (
              <div className="patient-feedback-choice">
                <span className="eyebrow">{t('先告诉医生你的感受')}</span>
                <h2>{t('这张图符合你的感受吗？')}</h2>
                <p>
                  {t('你可以选择满意并保持当前图像，或告诉医生哪些地方需要调整。')}
                </p>
                <div className="patient-feedback-choice__actions">
                  <Button
                    size="large"
                    icon={<FormOutlined />}
                    disabled={
                      feedbackSubmitting
                      || (adjustments?.used ?? 0) >= (adjustments?.limit ?? 3)
                    }
                    onClick={() => void chooseFeedbackMode('adjust')}
                  >
                    {t('调整')}
                  </Button>
                  <Button
                    type="primary"
                    size="large"
                    icon={<CheckCircleOutlined />}
                    loading={feedbackSubmitting}
                    onClick={() => void chooseFeedbackMode('satisfied')}
                  >
                    {t('满意')}
                  </Button>
                </div>
                {adjustmentError && (
                  <Alert type="warning" showIcon message={adjustmentError} />
                )}
                {(adjustments?.used ?? 0) >= (adjustments?.limit ?? 3) && (
                  <Alert
                    type="info"
                    showIcon
                    message={t('三次调整额度已使用完，仍可以选择满意并继续与医生讨论。')}
                  />
                )}
              </div>
            ) : feedbackMode === 'satisfied' ? (
              <div className="patient-feedback-satisfied">
                <CheckCircleOutlined />
                <span className="eyebrow">{t('本次不需要调整')}</span>
                <h2>{t('已选择满意')}</h2>
                <p>
                  {t('当前不会提交调整建议。如果改变想法，仍可以返回并告诉医生需要调整的地方。')}
                </p>
                <Button
                  size="large"
                  icon={<FormOutlined />}
                  loading={feedbackSubmitting}
                  disabled={(adjustments?.used ?? 0) >= (adjustments?.limit ?? 3)}
                  onClick={() => void chooseFeedbackMode('adjust')}
                >
                  {t('改为调整')}
                </Button>
              </div>
            ) : (
              <>
                <div className="patient-adjustment-panel__heading">
                  <div>
                    <span className="eyebrow">{t('告诉医生你的感受')}</span>
                    <h2>{t('这张图需要怎样调整？')}</h2>
                  </div>
                  <strong>{adjustments?.used ?? 0} / {adjustments?.limit ?? 3}</strong>
                </div>
                <Progress
                  percent={((adjustments?.used ?? 0) / (adjustments?.limit ?? 3)) * 100}
                  showInfo={false}
                  strokeColor="#5d7f78"
                  trailColor="#e8eeeb"
                />
                <p className="patient-adjustment-panel__hint">
                  {t('你可以提交最多 3 次调整建议。医生会先阅读并确认，再决定如何安全地调整图像。')}
                </p>
                <p className="patient-adjustment-panel__examples">
                  {t('你可以描述：年龄与性别呈现、脸型五官、肤色与皮肤、头发、表情眼神、服装、距离、光影、背景，或非人类与象征性特征。')}
                </p>
                <Input.TextArea
                  aria-label={t('外观调整建议')}
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder={t('例如：年龄更大、眼神更凶、脸型更瘦、头发更短、背景更暗')}
                  autoSize={{ minRows: 4, maxRows: 7 }}
                  maxLength={300}
                  showCount
                  disabled={Boolean(adjustments?.has_pending) || (adjustments?.used ?? 0) >= 3}
                />
                {adjustmentError && <Alert type="warning" showIcon message={adjustmentError} />}
                {success && <Alert type="success" showIcon message={success} />}
                <Button
                  type="primary"
                  size="large"
                  block
                  icon={<SendOutlined />}
                  loading={submitting}
                  disabled={
                    instruction.trim().length < 2 ||
                    Boolean(adjustments?.has_pending) ||
                    (adjustments?.used ?? 0) >= 3
                  }
                  onClick={() => void submitAdjustment()}
                >
                  {adjustments?.has_pending ? t('医生正在处理这条建议') : t('把建议告诉医生')}
                </Button>
                {!adjustments?.has_pending && (
                  <Button
                    className="patient-adjustment-back"
                    icon={<ArrowLeftOutlined />}
                    onClick={() => void chooseFeedbackMode('choice')}
                  >
                    {t('返回')}
                  </Button>
                )}
              </>
            )}

            {adjustments && adjustments.items.length > 0 && (
              <div className="patient-adjustment-history">
                <h3>{t('本次会话记录')}</h3>
                {adjustments.items.map((item) => (
                  <article key={item.request_id}>
                    <div className="patient-adjustment-history__meta">
                      <span>{language === 'en' ? `${t('第')}${item.sequence_no}` : `${t('第')} ${item.sequence_no} ${t('次调整')}`}</span>
                      <Tag color={adjustmentLabels[item.status].color}>
                        {t(adjustmentLabels[item.status].label)}
                      </Tag>
                    </div>
                    <p>{item.instruction}</p>
                    {item.status === 'rejected' && item.rejection_reason && (
                      <Alert
                        type="info"
                        showIcon
                        message={t('医生说明')}
                        description={item.rejection_reason}
                      />
                    )}
                  </article>
                ))}
              </div>
            )}
          </aside>
        </section>
      ) : (
        <section
          className={`waiting-panel waiting-panel--${session?.status ?? 'waiting_doctor'}`}
        >
          <div
            className={`waiting-visual waiting-visual--${session?.status ?? 'waiting_doctor'}`}
            aria-hidden="true"
          >
            <span className="waiting-ring waiting-ring--one" />
            <span className="waiting-ring waiting-ring--two" />
            <span className="waiting-ring waiting-ring--three" />
            {session?.status === 'ended' ? (
              <CheckCircleOutlined className="waiting-visual__state-icon" />
            ) : (
              <i />
            )}
          </div>
          <span className="eyebrow">
            {t(
              session?.status === 'active'
                ? reusingPrevious
                  ? '沿用上次记录'
                  : '访谈已经开始'
                : copy.eyebrow,
            )}
          </span>
          <h1>
            {t(
              session?.status === 'active'
                ? reusingPrevious
                  ? '医生正在调取上次的记录'
                  : '请根据医生的提问，回答问题'
                : copy.title,
            )}
          </h1>
          <p>
            {t(
              session?.status === 'active'
                ? reusingPrevious
                  ? '你不需要再次回答 Q1–Q8。请稍候，医生会和你一起继续查看上次的视觉表达；如果这次感受有变化，也可以直接告诉医生。'
                  : '请放松，不需要担心回答得是否正确。请按照医生的提问，根据自己的真实感受回答；如果感到不舒服，可以随时告诉医生并暂停。'
                : copy.copy,
            )}
          </p>
          {error && <Alert type="warning" showIcon message={error} />}
          <div className="waiting-status">
            <span />{' '}
            {t(
              session?.status === 'active'
                ? reusingPrevious
                  ? '医生正在准备上次的记录'
                  : '医生正在陪你完成访谈'
                : session?.status === 'ended'
                  ? '会话已结束'
                  : session?.status === 'expired'
                    ? '会话已过期'
                    : session?.status === 'paused'
                      ? '会话已暂停'
                      : '医生正在为你准备',
            )}
          </div>
        </section>
      )}

      {session?.status === 'active' && (
        <Button
          className="patient-safety-button"
          danger
          type="text"
          onClick={() => setPauseOpen(true)}
          icon={<ExclamationCircleOutlined />}
        >
          {t('我感到不适，需要暂停')}
        </Button>
      )}
      <footer className="patient-session-footer">{t('这是帮助你表达感受的辅助工具，不代表诊断结果，也不能替代治疗')}</footer>
      <Modal
        title={t('要先暂停一下吗？')}
        open={pauseOpen}
        okText={t('暂停并通知医生')}
        cancelText={t('返回会话')}
        okButtonProps={{ danger: true, loading: pausing }}
        onCancel={() => setPauseOpen(false)}
        onOk={() => void pauseSession()}
      >
        <p>{t('暂停后页面内容会暂时隐藏，只有身边的医生可以恢复。请同时把你的感受告诉医生。')}</p>
      </Modal>
      <Modal
        title={t('会话已结束')}
        open={endedNoticeOpen}
        okText={t('知道了')}
        cancelButtonProps={{ style: { display: 'none' } }}
        closable={false}
        maskClosable={false}
        onOk={leaveEndedSession}
      >
        <p>{t('会话已结束，感谢您的参与及配合！')}</p>
        <p>{t('谢谢你的参与。接下来可以继续和医生讨论感受；如需再次进入，医生会提供新的邀请码。')}</p>
      </Modal>
    </main>
  )
}
