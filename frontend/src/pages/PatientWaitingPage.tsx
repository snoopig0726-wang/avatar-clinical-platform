import {
  ExclamationCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Alert, Button, Input, Modal, Progress, Spin, Tag } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  ApiClientError,
  apiRequest,
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
    eyebrow: '会话已连接',
    title: '正在等待医生开始',
    copy: '请留在当前页面。医生确认当面知情同意并启动会话后，这里会自动更新。',
  },
  active: {
    eyebrow: '医生已授权',
    title: '当前 Avatar',
    copy: '这是对声音描述的低刺激视觉表达，你可以在现场医生陪同下提出调整。',
  },
  paused: {
    eyebrow: '安全暂停已生效',
    title: '当前会话已暂停',
    copy: '内容访问和后续交互已经停止。请告知身边的医生，只有医生可以恢复。',
  },
  ended: {
    eyebrow: '会话已结束',
    title: '本次受监督会话已经结束',
    copy: '当前凭证已经失效。如需再次进入，请由医生创建新的邀请码。',
  },
  expired: {
    eyebrow: '会话已过期',
    title: '当前会话凭证已失效',
    copy: '请联系现场医生重新创建邀请码。',
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
  const [pauseOpen, setPauseOpen] = useState(false)
  const [session, setSession] = useState<PatientSession | null>(null)
  const [avatar, setAvatar] = useState<PatientAvatar | null>(null)
  const [adjustments, setAdjustments] = useState<PatientAdjustmentList | null>(null)
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(true)
  const [pausing, setPausing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [adjustmentError, setAdjustmentError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

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
      setError(requestError instanceof Error ? requestError.message : '授权内容暂时无法加载')
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
      if (result.status === 'active') await loadAuthorizedContent()
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError
          ? requestError.message
          : '暂时无法同步会话状态，请保持当前页面',
      )
    } finally {
      setLoading(false)
    }
  }, [loadAuthorizedContent, navigate, patientToken, sessionId])

  useEffect(() => {
    void loadSession()
    const timer = window.setInterval(() => void loadSession(), 5000)
    return () => window.clearInterval(timer)
  }, [loadSession])

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
      setError(requestError instanceof ApiClientError ? requestError.message : '暂停请求未能完成')
    } finally {
      setPausing(false)
    }
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
        requestError instanceof ApiClientError ? requestError.message : '调整建议未能提交，请稍后重试',
      )
    } finally {
      setSubmitting(false)
    }
  }

  const copy = sessionCopy[session?.status ?? 'waiting_doctor']
  const activeAuthorized = session?.status === 'active' && avatar

  return (
    <main className="patient-session-page">
      <header className="patient-session-header">
        <Brand compact />
        <span><LockOutlined /> 当前设备 · 受监督会话</span>
      </header>

      {loading ? (
        <section className="waiting-panel"><Spin size="large" tip="正在安全连接会话…" /></section>
      ) : activeAuthorized ? (
        <section className="patient-avatar-workspace">
          <div className="patient-avatar-stage">
            <div className="patient-avatar-stage__heading">
              <div>
                <span className="eyebrow">{copy.eyebrow}</span>
                <h1>{copy.title}</h1>
              </div>
              <Tag color="success" icon={<SafetyCertificateOutlined />}>医生已审核并授权</Tag>
            </div>
            {avatar.display_mode === 'image' && avatar.image_url ? (
              <div className="patient-avatar-portrait patient-avatar-portrait--image">
                <img src={avatar.image_url} alt="医生已审核授权的 Avatar" />
              </div>
            ) : (
              <div className="patient-avatar-portrait" aria-label="Avatar 图像暂不可用">
                <span className="patient-avatar-portrait__halo" />
                <UserOutlined />
                <span className="patient-avatar-portrait__caption">低刺激视觉占位</span>
              </div>
            )}
            <p className="patient-avatar-stage__copy">{copy.copy}</p>
            {avatar.message && <Alert type="info" showIcon message={avatar.message} />}
          </div>

          <aside className="patient-adjustment-panel">
            <div className="patient-adjustment-panel__heading">
              <div>
                <span className="eyebrow">可选操作</span>
                <h2>提出外观调整</h2>
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
              每个病例终身最多提交 3 次。内容通过安全校验后仍需医生审核，不会直接进入图像模型。
            </p>
            <Input.TextArea
              aria-label="外观调整建议"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="例如：希望表情更平静、背景更柔和"
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
              {adjustments?.has_pending ? '等待医生处理当前建议' : '提交给现场医生审核'}
            </Button>

            {adjustments && adjustments.items.length > 0 && (
              <div className="patient-adjustment-history">
                <h3>本次会话记录</h3>
                {adjustments.items.map((item) => (
                  <div key={item.request_id}>
                    <span>第 {item.sequence_no} 次调整</span>
                    <Tag color={adjustmentLabels[item.status].color}>
                      {adjustmentLabels[item.status].label}
                    </Tag>
                  </div>
                ))}
              </div>
            )}
          </aside>
        </section>
      ) : (
        <section className="waiting-panel">
          <div className="waiting-visual" aria-hidden="true">
            <span className="waiting-ring waiting-ring--one" />
            <span className="waiting-ring waiting-ring--two" />
            <span className="waiting-ring waiting-ring--three" />
            <i />
          </div>
          <span className="eyebrow">{copy.eyebrow}</span>
          <h1>{copy.title}</h1>
          <p>{session?.status === 'active' ? '医生尚未授权可供查看的 Avatar，请保持当前页面。' : copy.copy}</p>
          {error && <Alert type="warning" showIcon message={error} />}
          <div className="waiting-status"><span /> 等待医生处理</div>
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
          我感到不适，需要暂停
        </Button>
      )}
      <footer className="patient-session-footer">这是非诊断、非真实身份复刻的视觉表达</footer>
      <Modal
        title="确认安全暂停"
        open={pauseOpen}
        okText="暂停并通知医生"
        cancelText="返回会话"
        okButtonProps={{ danger: true, loading: pausing }}
        onCancel={() => setPauseOpen(false)}
        onOk={() => void pauseSession()}
      >
        <p>暂停后你将停止访问会话内容，只有现场医生可以恢复。请同时告知身边的医生。</p>
      </Modal>
    </main>
  )
}
