import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  FormOutlined,
  HistoryOutlined,
  KeyOutlined,
  PauseCircleOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Empty,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Timeline,
  message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  ApiClientError,
  apiRequest,
  downloadApiFile,
  type AvatarVersion,
  type AvatarVersionList,
  type ClinicalCase,
  type DoctorAdjustment,
  type DoctorAdjustmentList,
  type InviteListResponse,
  newIdempotencyKey,
  type PatientSession,
  type SessionInvite,
  staffTokenStore,
  type VisualFeatures,
} from '../lib/api'

const inviteLabels: Record<SessionInvite['status'], string> = {
  issued: '待兑换',
  redeemed_waiting: '患者等待医生',
  active: '会话进行中',
  ended: '已结束',
  revoked: '已撤销',
  expired: '已过期',
}

const sessionLabels: Record<PatientSession['status'], string> = {
  waiting_doctor: '等待医生开始',
  active: '进行中',
  paused: '安全暂停',
  ended: '已结束',
  expired: '已过期',
}

const adjustmentStatusLabels: Record<DoctorAdjustment['status'], string> = {
  pending_doctor_review: '等待医生审核',
  approved_as_is: '已原样接受',
  approved_edited: '已编辑后接受',
  rejected: '已拒绝',
  generating: '正在生成',
  applied: '已应用',
  generation_failed: '生成失败',
  cancelled: '已取消',
}

const generationStatusLabels: Record<AvatarVersion['generation_status'], string> = {
  queued: '排队中',
  generating: 'GPT Image 2 生成中',
  checking: '图片安全检查中',
  pending_doctor_review: '等待医生审核',
  approved: '已审核并可授权',
  rejected: '医生已拒绝',
  failed: '生成未完成',
  cancelled: '已取消',
}

export function DoctorCasePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const [messageApi, messageContext] = message.useMessage()
  const [clinicalCase, setClinicalCase] = useState<ClinicalCase | null>(null)
  const [invites, setInvites] = useState<SessionInvite[]>([])
  const [sessions, setSessions] = useState<Record<string, PatientSession>>({})
  const [adjustments, setAdjustments] = useState<DoctorAdjustmentList | null>(null)
  const [visualFeatures, setVisualFeatures] = useState<VisualFeatures | null>(null)
  const [avatarVersions, setAvatarVersions] = useState<AvatarVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createdInvite, setCreatedInvite] = useState<SessionInvite | null>(null)
  const [startTarget, setStartTarget] = useState<PatientSession | null>(null)
  const [consentConfirmed, setConsentConfirmed] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [working, setWorking] = useState(false)
  const [editTarget, setEditTarget] = useState<DoctorAdjustment | null>(null)
  const [controlledInstruction, setControlledInstruction] = useState<string | null>(null)

  const loadCase = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token || !caseId) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [caseResult, inviteResult, adjustmentResult, versionResult, visualResult] = await Promise.all([
        apiRequest<ClinicalCase>(`/cases/${caseId}`, { staffToken: token }),
        apiRequest<InviteListResponse>(`/cases/${caseId}/session-invites`, {
          staffToken: token,
        }),
        apiRequest<DoctorAdjustmentList>(`/cases/${caseId}/adjustment-requests`, {
          staffToken: token,
        }),
        apiRequest<AvatarVersionList>(`/cases/${caseId}/avatar-versions`, {
          staffToken: token,
        }),
        apiRequest<VisualFeatures>(`/cases/${caseId}/visual-features`, {
          staffToken: token,
        }).catch((requestError: unknown) => {
          if (requestError instanceof ApiClientError && requestError.status === 409) return null
          throw requestError
        }),
      ])
      const sessionResults = await Promise.all(
        inviteResult.items
          .filter((item) => item.session_id)
          .map((item) =>
            apiRequest<PatientSession>(`/sessions/${item.session_id}`, { staffToken: token }),
          ),
      )
      setClinicalCase(caseResult)
      setInvites(inviteResult.items)
      setSessions(Object.fromEntries(sessionResults.map((item) => [item.session_id, item])))
      setAdjustments(adjustmentResult)
      setAvatarVersions(versionResult.items)
      setVisualFeatures(visualResult)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
        return
      }
      setError(requestError instanceof Error ? requestError.message : '病例加载失败')
    } finally {
      setLoading(false)
    }
  }, [caseId, navigate])

  useEffect(() => void loadCase(), [loadCase])

  useEffect(() => {
    if (!avatarVersions.some((item) => ['queued', 'generating', 'checking'].includes(item.generation_status))) return
    const timer = window.setInterval(() => void loadCase(), 3000)
    return () => window.clearInterval(timer)
  }, [avatarVersions, loadCase])

  async function createInvite() {
    const token = staffTokenStore.get()
    if (!token || !caseId) return
    setWorking(true)
    try {
      const result = await apiRequest<SessionInvite>(`/cases/${caseId}/session-invites`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('invite-create'),
        body: { expires_in_hours: 24 },
      })
      setInvites((current) => [result, ...current])
      setCreatedInvite(result)
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '邀请码创建失败')
    } finally {
      setWorking(false)
    }
  }

  async function controlSession(
    target: PatientSession,
    action: 'start' | 'resume' | 'stop',
  ) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      const body =
        action === 'start'
          ? { consent_confirmed: true, consent_version: 'v1' }
          : action === 'stop'
            ? { reason: 'doctor_ended' }
            : {}
      const result = await apiRequest<PatientSession>(
        `/sessions/${target.session_id}/${action}`,
        {
          method: 'POST',
          staffToken: token,
          idempotencyKey: newIdempotencyKey(`session-${action}`),
          body,
        },
      )
      setSessions((current) => ({ ...current, [result.session_id]: result }))
      setStartTarget(null)
      setConsentConfirmed(false)
      messageApi.success(action === 'start' ? '会话已启动' : action === 'resume' ? '会话已恢复' : '会话已结束')
      void loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '操作失败')
    } finally {
      setWorking(false)
    }
  }

  async function archiveCase() {
    const token = staffTokenStore.get()
    if (!token || !caseId) return
    setWorking(true)
    try {
      const result = await apiRequest<ClinicalCase>(`/cases/${caseId}/archive`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('case-archive'),
        body: { reason: 'doctor_archived' },
      })
      setClinicalCase(result)
      setArchiveOpen(false)
      messageApi.success('病例已归档，30 天删除倒计时已经开始')
      void loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '归档失败')
    } finally {
      setWorking(false)
    }
  }

  async function reviewAdjustment(
    target: DoctorAdjustment,
    decision: 'approve_as_is' | 'approve_edited' | 'reject',
  ) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<DoctorAdjustment>(`/adjustment-requests/${target.request_id}/review`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('adjustment-review'),
        body: {
          decision,
          controlled_instruction: decision === 'approve_edited' ? controlledInstruction : null,
        },
      })
      setEditTarget(null)
      setControlledInstruction(null)
      messageApi.success(
        decision === 'reject' ? '已拒绝该调整建议' : '审核已保存，可以生成调整版本',
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '审核未能保存')
    } finally {
      setWorking(false)
    }
  }

  async function generateAvatar(mode: 'initial' | 'same_features_regenerate' | 'feature_update') {
    const token = staffTokenStore.get()
    if (!token || !caseId) return
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/cases/${caseId}/avatar-generations`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-generate'),
        body: { mode },
      })
      messageApi.success('生图任务已提交，完成后需要医生审核才会展示给患者')
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '生图任务提交失败')
    } finally {
      setWorking(false)
    }
  }

  async function cancelGeneration(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/avatar-versions/${target.version_id}/cancel`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-cancel'),
        body: { reason: 'doctor_cancelled' },
      })
      messageApi.info(`第 ${target.generation_round} 版生成任务已取消`)
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '生成任务取消失败')
    } finally {
      setWorking(false)
    }
  }

  async function generateAdjustment(target: DoctorAdjustment) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/adjustment-requests/${target.request_id}/generate`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('adjustment-generate'),
      })
      messageApi.success('调整版本已进入生图和安全检查流程')
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '调整版本生成失败')
    } finally {
      setWorking(false)
    }
  }

  async function reviewAvatar(target: AvatarVersion, decision: 'approve' | 'reject') {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/avatar-versions/${target.version_id}/review`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-review'),
        body: { decision },
      })
      messageApi.success(
        decision === 'approve'
          ? '审核已通过；还需单独授权后患者才能查看'
          : '该版本已拒绝',
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '版本审核失败')
    } finally {
      setWorking(false)
    }
  }

  async function authorizeVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning('请先启动本病例的患者监督会话')
      return
    }
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/avatar-versions/${target.version_id}/authorize`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-authorize'),
        body: { session_id: activeSession.session_id },
      })
      messageApi.success(`已授权第 ${target.generation_round} 版，患者端现在可以查看`)
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '版本授权失败')
    } finally {
      setWorking(false)
    }
  }

  async function rollbackVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning('请先启动本病例的患者监督会话')
      return
    }
    setWorking(true)
    try {
      await apiRequest<AvatarVersion>(`/avatar-versions/${target.version_id}/rollback`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-rollback'),
        body: { session_id: activeSession.session_id },
      })
      messageApi.warning(
        `已选择第 ${target.generation_round} 版作为回退候选，旧授权已撤销；请重新审核后再授权`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '版本回退失败')
    } finally {
      setWorking(false)
    }
  }

  async function downloadVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      const file = await downloadApiFile(
        `/cases/${target.case_id}/avatar-versions/${target.version_id}/download`,
        token,
      )
      const url = URL.createObjectURL(file.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = file.filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      messageApi.success('指定版本和对应 Q1–Q8 快照已下载，操作已记录审计')
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '版本下载失败')
    } finally {
      setWorking(false)
    }
  }

  async function revokeAuthorization(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token || !caseId) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning('没有可撤销授权的进行中监督会话')
      return
    }
    setWorking(true)
    try {
      await apiRequest(`/cases/${caseId}/authorization/revoke`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-authorization-revoke'),
        body: {
          session_id: activeSession.session_id,
          reason: 'doctor_manual_revoke',
        },
      })
      messageApi.success(`已撤销第 ${target.generation_round} 版的患者展示授权`)
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '授权撤销失败')
    } finally {
      setWorking(false)
    }
  }

  const generationRunning = avatarVersions.some((item) =>
    ['queued', 'generating', 'checking'].includes(item.generation_status),
  )

  if (loading) {
    return <div className="route-fallback"><Spin size="large" tip="正在加载病例…" /></div>
  }

  return (
    <div className="case-page">
      {messageContext}
      <header className="case-page__header">
        <Brand />
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/doctor/workspace')}>
          返回工作台
        </Button>
      </header>
      <main className="case-page__content">
        {error && <Alert type="error" showIcon message="病例暂时不可用" description={error} />}
        {clinicalCase && (
          <>
            <div className="case-page__title">
              <div>
                <span className="eyebrow">去标识化病例</span>
                <h1>{clinicalCase.study_code}</h1>
                <p>医生拥有和监督 · 患者端不可查看病例导航及历史记录</p>
              </div>
              <Space>
                <Tag color={clinicalCase.status === 'in_progress' ? 'processing' : 'default'}>
                  {clinicalCase.status === 'draft' ? '草稿' : clinicalCase.status === 'in_progress' ? '进行中' : clinicalCase.status === 'completed' ? '已完成' : '已归档'}
                </Tag>
                <Button
                  danger
                  disabled={clinicalCase.status === 'archived'}
                  onClick={() => setArchiveOpen(true)}
                >
                  归档病例
                </Button>
              </Space>
            </div>

            {clinicalCase.retention_due_at && (
              <Alert
                type="warning"
                showIcon
                message={
                  clinicalCase.status === 'archived'
                    ? '病例已归档'
                    : '该病例已恢复，但永久删除倒计时仍在继续'
                }
                description={`永久删除时间：${new Date(clinicalCase.retention_due_at).toLocaleString('zh-CN')}。恢复不会暂停或重置倒计时，旧患者会话也不会恢复。`}
              />
            )}

            <div className="case-detail-grid">
              <Card title="监督会话与邀请码" className="case-session-card" extra={<Button type="primary" icon={<KeyOutlined />} disabled={clinicalCase.status === 'archived'} loading={working} onClick={() => void createInvite()}>创建邀请码</Button>}>
                {invites.length === 0 ? (
                  <Empty description="尚未创建邀请码" />
                ) : (
                  <div className="invite-list">
                    {invites.map((invite) => {
                      const patientSession = invite.session_id ? sessions[invite.session_id] : null
                      return (
                        <article className="invite-list__item" key={invite.invite_id}>
                          <div className="invite-list__main">
                            <span className="invite-list__icon"><KeyOutlined /></span>
                            <div>
                              <strong>{invite.code ?? invite.code_mask}</strong>
                              <p>有效至 {new Date(invite.expires_at).toLocaleString('zh-CN')}</p>
                            </div>
                          </div>
                          <div className="invite-list__actions">
                            <Tag>{inviteLabels[invite.status]}</Tag>
                            {invite.code && <Button type="text" icon={<CopyOutlined />} onClick={() => navigator.clipboard.writeText(invite.code!)}>复制</Button>}
                            {patientSession?.status === 'waiting_doctor' && <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setStartTarget(patientSession)}>确认并开始</Button>}
                            {patientSession?.status === 'paused' && <Button type="primary" icon={<PlayCircleOutlined />} loading={working} onClick={() => void controlSession(patientSession, 'resume')}>医生恢复</Button>}
                            {patientSession?.status === 'active' && <Button icon={<FormOutlined />} onClick={() => navigate(`/doctor/cases/${caseId}/interview/${patientSession.session_id}`)}>录入 Q1–Q8</Button>}
                            {patientSession?.status === 'active' && <Button danger icon={<StopOutlined />} loading={working} onClick={() => void controlSession(patientSession, 'stop')}>结束会话</Button>}
                          </div>
                          {patientSession && (
                            <div className="session-inline-status">
                              {patientSession.status === 'paused' ? <PauseCircleOutlined /> : <ClockCircleOutlined />}
                              <span>会话状态：{sessionLabels[patientSession.status]}</span>
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </div>
                )}
              </Card>

              <Card title="本病例工作流" className="case-flow-card">
                <Timeline
                  items={[
                    { color: 'green', dot: <CheckCircleOutlined />, children: '病例已创建并归属当前医生' },
                    { color: invites.length ? 'green' : 'gray', children: '患者兑换一次性邀请码' },
                    { color: Object.values(sessions).some((item) => item.started_at) ? 'green' : 'gray', children: '医生确认当面知情同意并启动' },
                    { color: 'gray', children: '录入并确认 Q1–Q8 视觉映射' },
                    { color: avatarVersions.length ? 'green' : 'gray', children: 'GPT Image 2 生成、图片安全检查与医生授权' },
                  ]}
                />
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="创建时间">{new Date(clinicalCase.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
                  <Descriptions.Item label="活动会话">{clinicalCase.active_session_count}</Descriptions.Item>
                  <Descriptions.Item label="数据边界">不保存患者身份信息</Descriptions.Item>
                </Descriptions>
              </Card>
            </div>

            <Card
              className="avatar-generation-card"
              title="Avatar 生成与版本审核"
              extra={
                <Space wrap>
                  <Tag color={visualFeatures?.is_doctor_confirmed ? 'success' : 'warning'}>
                    {visualFeatures?.is_doctor_confirmed ? '视觉特征已确认' : '等待确认视觉特征'}
                  </Tag>
                  <Button
                    type="primary"
                    icon={avatarVersions.length ? <ReloadOutlined /> : <PictureOutlined />}
                    disabled={
                      !visualFeatures?.is_doctor_confirmed
                      || clinicalCase.status === 'archived'
                      || generationRunning
                    }
                    loading={working}
                    onClick={() => void generateAvatar(avatarVersions.length ? 'same_features_regenerate' : 'initial')}
                  >
                    {generationRunning
                      ? '当前版本生成中'
                      : avatarVersions.length
                        ? '按相同特征重新生成'
                        : '生成首版 Avatar'}
                  </Button>
                </Space>
              }
            >
              {!visualFeatures?.is_doctor_confirmed && (
                <Alert
                  type="info"
                  showIcon
                  message="完成 Q1–Q8 映射并由医生确认后，才能提交生图任务"
                  description="字段校验和声音到视觉映射不会自动触发生图。"
                />
              )}
              {avatarVersions.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无生成版本" />
              ) : (
                <div className="avatar-version-grid">
                  {avatarVersions.map((version) => (
                    <article className="avatar-version-card" key={version.version_id}>
                      <div className="avatar-version-card__preview">
                        {version.image_url ? (
                          <img src={version.image_url} alt={`Avatar 第 ${version.generation_round} 版`} />
                        ) : (
                          <div className="avatar-version-card__empty"><PictureOutlined /></div>
                        )}
                        <span>V{version.generation_round}</span>
                      </div>
                      <div className="avatar-version-card__body">
                        <div className="avatar-version-card__title">
                          <strong>第 {version.generation_round} 版</strong>
                          <Tag
                            color={
                              version.generation_status === 'approved'
                                ? 'success'
                                : version.generation_status === 'failed'
                                  ? 'error'
                                  : version.generation_status === 'cancelled'
                                    ? 'default'
                                    : 'processing'
                            }
                          >
                            {generationStatusLabels[version.generation_status]}
                          </Tag>
                        </div>
                        <p>{version.provider_model} · {version.prompt_template_version}</p>
                        {version.failure_code && <Alert type="warning" showIcon message={`失败代码：${version.failure_code}`} />}
                        {['queued', 'generating', 'checking'].includes(version.generation_status) && (
                          <Button
                            danger
                            icon={<StopOutlined />}
                            loading={working}
                            onClick={() =>
                              Modal.confirm({
                                title: `取消第 ${version.generation_round} 版生成？`,
                                content: '已经生成但尚未采用的临时图片会被丢弃，不影响此前已审核版本。',
                                okText: '确认取消',
                                cancelText: '继续生成',
                                okButtonProps: { danger: true },
                                onOk: () => cancelGeneration(version),
                              })
                            }
                          >
                            取消生成
                          </Button>
                        )}
                        {version.generation_status === 'failed' && (
                          <Button
                            icon={<ReloadOutlined />}
                            loading={working}
                            disabled={generationRunning}
                            onClick={() => void generateAvatar('same_features_regenerate')}
                          >
                            按相同特征重试
                          </Button>
                        )}
                        {version.generation_status === 'pending_doctor_review' && (
                          <Space wrap>
                            <Button type="primary" icon={<SafetyCertificateOutlined />} loading={working} onClick={() => void reviewAvatar(version, 'approve')}>
                              审核通过
                            </Button>
                            <Button danger icon={<CloseOutlined />} loading={working} onClick={() => void reviewAvatar(version, 'reject')}>
                              拒绝此图
                            </Button>
                          </Space>
                        )}
                        {version.generation_status === 'approved' && (
                          <Space wrap>
                            {version.is_authorized ? (
                              <>
                                <Tag color="success" icon={<CheckCircleOutlined />}>患者当前可见</Tag>
                                <Button
                                  danger
                                  icon={<StopOutlined />}
                                  loading={working}
                                  onClick={() => void revokeAuthorization(version)}
                                >
                                  撤销患者授权
                                </Button>
                              </>
                            ) : version.is_current_candidate ? (
                              <Button type="primary" icon={<CheckCircleOutlined />} loading={working} onClick={() => void authorizeVersion(version)}>
                                授权患者查看
                              </Button>
                            ) : (
                              <Button
                                icon={<HistoryOutlined />}
                                loading={working}
                                onClick={() =>
                                  Modal.confirm({
                                    title: `回退到第 ${version.generation_round} 版？`,
                                    content: '当前患者授权将立即撤销。该历史版本必须重新审核并再次授权后，患者才能查看。',
                                    okText: '确认回退',
                                    cancelText: '取消',
                                    okButtonProps: { danger: true },
                                    onOk: () => rollbackVersion(version),
                                  })
                                }
                              >
                                选择此版回退
                              </Button>
                            )}
                            {version.snapshot_available && version.image_url && (
                              <Button icon={<DownloadOutlined />} loading={working} onClick={() => void downloadVersion(version)}>
                                下载此版
                              </Button>
                            )}
                          </Space>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </Card>

            <Card
              className="doctor-adjustment-card"
              title="患者外观调整审核"
              extra={<Tag>{adjustments?.used ?? 0} / {adjustments?.limit ?? 3} 次额度已使用</Tag>}
            >
              {!adjustments || adjustments.items.length === 0 ? (
                <Empty description="患者尚未提交调整建议" />
              ) : (
                <div className="doctor-adjustment-list">
                  {adjustments.items.map((item) => (
                    <article key={item.request_id}>
                      <div className="doctor-adjustment-list__meta">
                        <span>
                          第 {item.sequence_no} 次 · {new Date(item.submitted_at).toLocaleString('zh-CN')}
                        </span>
                        <Tag
                          color={
                            item.status === 'pending_doctor_review'
                              ? 'processing'
                              : item.status === 'rejected'
                                ? 'default'
                                : 'blue'
                          }
                        >
                          {adjustmentStatusLabels[item.status]}
                        </Tag>
                      </div>
                      <blockquote>{item.instruction}</blockquote>
                      {item.controlled_instruction && (
                        <div className="controlled-instruction">
                          <SafetyCertificateOutlined /> 受控指令：{item.controlled_instruction}
                        </div>
                      )}
                      {item.status === 'pending_doctor_review' && (
                        <Space wrap>
                          <Button
                            type="primary"
                            icon={<CheckCircleOutlined />}
                            loading={working}
                            onClick={() => void reviewAdjustment(item, 'approve_as_is')}
                          >
                            接受并转换为受控指令
                          </Button>
                          <Button
                            icon={<FormOutlined />}
                            onClick={() => {
                              setEditTarget(item)
                              setControlledInstruction(adjustments.controlled_options[0] ?? null)
                            }}
                          >
                            选择受控调整后接受
                          </Button>
                          <Button
                            danger
                            icon={<CloseOutlined />}
                            loading={working}
                            onClick={() => void reviewAdjustment(item, 'reject')}
                          >
                            拒绝
                          </Button>
                        </Space>
                      )}
                      {(item.status === 'approved_as_is' || item.status === 'approved_edited') && (
                        <Button
                          type="primary"
                          icon={<PictureOutlined />}
                          loading={working}
                          onClick={() => void generateAdjustment(item)}
                        >
                          生成受控调整版本
                        </Button>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </Card>
          </>
        )}
      </main>

      <Modal title="确认已完成当面知情同意" open={Boolean(startTarget)} onCancel={() => setStartTarget(null)} okText="确认并启动会话" okButtonProps={{ disabled: !consentConfirmed, loading: working }} onOk={() => startTarget && void controlSession(startTarget, 'start')}>
        <Alert type="info" showIcon icon={<SafetyCertificateOutlined />} message="该确认由当前医生完成" description="系统只保存确认医生、确认时间和同意文本版本，不要求患者在线签名。" />
        <Checkbox className="consent-check" checked={consentConfirmed} onChange={(event) => setConsentConfirmed(event.target.checked)}>
          我已在现场向患者说明研究用途、展示边界和安全暂停方式，并确认其同意继续。
        </Checkbox>
      </Modal>

      <Modal
        title="选择受控调整后接受"
        open={Boolean(editTarget)}
        onCancel={() => {
          setEditTarget(null)
          setControlledInstruction(null)
        }}
        okText="确认接受"
        okButtonProps={{ disabled: !controlledInstruction, loading: working }}
        onOk={() => editTarget && void reviewAdjustment(editTarget, 'approve_edited')}
      >
        <Alert
          type="info"
          showIcon
          message="患者原文不会进入图像模型"
          description="请选择一条低刺激受控指令。后续仅该指令可进入生图流程。"
        />
        <Select
          className="controlled-instruction-select"
          value={controlledInstruction}
          options={(adjustments?.controlled_options ?? []).map((option) => ({
            value: option,
            label: option,
          }))}
          onChange={setControlledInstruction}
        />
      </Modal>

      <Modal title="归档病例" open={archiveOpen} onCancel={() => setArchiveOpen(false)} okText="确认归档" okButtonProps={{ danger: true, loading: working }} onOk={() => void archiveCase()}>
        <p>归档会立即结束所有患者会话，并从现在起启动 30 天永久删除倒计时。</p>
      </Modal>

      <Modal title="一次性患者邀请码" open={Boolean(createdInvite)} onCancel={() => setCreatedInvite(null)} footer={<Button type="primary" onClick={() => setCreatedInvite(null)}>完成</Button>}>
        <Alert type="success" showIcon message="邀请码已创建" description="仅在现场监督会话中提供；兑换后不能再次使用。" />
        <div className="invite-code-display">{createdInvite?.code}</div>
        <Button block icon={<CopyOutlined />} onClick={() => createdInvite?.code && navigator.clipboard.writeText(createdInvite.code)}>复制邀请码</Button>
      </Modal>
    </div>
  )
}
