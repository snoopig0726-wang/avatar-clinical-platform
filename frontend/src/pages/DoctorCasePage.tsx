import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  DeleteOutlined,
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
  Input,
  Modal,
  Radio,
  Space,
  Spin,
  Tag,
  Timeline,
  message,
} from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { localizeControlledInstruction } from '../i18n/controlledInstructions'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  downloadApiFile,
  type AvatarVersion,
  type AvatarVersionList,
  type CaseSafetyEvent,
  type CaseSafetyEventListResponse,
  type ClinicalCase,
  type DoctorAdjustment,
  type DoctorAdjustmentList,
  type DeleteAvatarVersionResponse,
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
  generating: '正在生成视觉表达',
  checking: '图片安全检查中',
  pending_doctor_review: '等待医生审核',
  approved: '已审核并可授权',
  rejected: '医生已拒绝',
  failed: '生成未完成',
  cancelled: '已取消',
}

type CaseFlowState = 'complete' | 'current' | 'pending' | 'skipped'

type CaseFlowStep = {
  key: string
  label: string
  detail: string
  state: CaseFlowState
}

export function DoctorCasePage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const dateLocale = language === 'en' ? 'en-US' : language
  const [messageApi, messageContext] = message.useMessage()
  const [clinicalCase, setClinicalCase] = useState<ClinicalCase | null>(null)
  const [invites, setInvites] = useState<SessionInvite[]>([])
  const [sessions, setSessions] = useState<Record<string, PatientSession>>({})
  const [adjustments, setAdjustments] = useState<DoctorAdjustmentList | null>(null)
  const [safetyEvents, setSafetyEvents] = useState<CaseSafetyEvent[]>([])
  const [visualFeatures, setVisualFeatures] = useState<VisualFeatures | null>(null)
  const [avatarVersions, setAvatarVersions] = useState<AvatarVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createdInvite, setCreatedInvite] = useState<SessionInvite | null>(null)
  const [startTarget, setStartTarget] = useState<PatientSession | null>(null)
  const [consentConfirmed, setConsentConfirmed] = useState(false)
  const [assessmentMode, setAssessmentMode] = useState<
    'new_assessment' | 'reuse_previous' | null
  >(null)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [working, setWorking] = useState(false)
  const [adjustTarget, setAdjustTarget] = useState<DoctorAdjustment | null>(null)
  const [selectedControlledInstruction, setSelectedControlledInstruction] = useState('')
  const [rejectTarget, setRejectTarget] = useState<DoctorAdjustment | null>(null)
  const [rejectionReason, setRejectionReason] = useState('')
  const knownAdjustmentIds = useRef<Set<string> | null>(null)
  const knownSafetyEventIds = useRef<Set<number> | null>(null)
  const knownSatisfiedSessionIds = useRef<Set<string> | null>(null)
  const liveCaseRefreshRunning = useRef(false)

  const loadCase = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token || !caseId) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [caseResult, inviteResult, adjustmentResult, versionResult, visualResult, safetyResult] = await Promise.all([
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
        apiRequest<CaseSafetyEventListResponse>(
          `/cases/safety-events/recent?case_id=${caseId}`,
          { staffToken: token },
        ),
      ])
      const visibleInvites = inviteResult.items.filter((item) => item.status !== 'revoked')
      const sessionResults = await Promise.all(
        visibleInvites
          .filter((item) => item.session_id)
          .map((item) =>
            apiRequest<PatientSession>(`/sessions/${item.session_id}`, { staffToken: token }),
          ),
      )
      setClinicalCase(caseResult)
      setInvites(visibleInvites)
      setSessions(Object.fromEntries(sessionResults.map((item) => [item.session_id, item])))
      knownSatisfiedSessionIds.current = new Set(
        sessionResults
          .filter((item) => item.patient_satisfied_version_id)
          .map((item) => item.session_id),
      )
      setAdjustments(adjustmentResult)
      knownAdjustmentIds.current = new Set(
        adjustmentResult.items.map((item) => item.request_id),
      )
      setSafetyEvents(safetyResult.items)
      knownSafetyEventIds.current = new Set(
        safetyResult.items.map((item) => item.event_id),
      )
      setAvatarVersions(versionResult.items)
      setVisualFeatures(visualResult)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
        return
      }
      setError(requestError instanceof Error ? requestError.message : t('病例加载失败'))
    } finally {
      setLoading(false)
    }
  }, [caseId, navigate, t])

  const loadLiveCase = useCallback(async () => {
    const token = staffTokenStore.get()
    if (
      !token
      || !caseId
      || document.visibilityState !== 'visible'
      || liveCaseRefreshRunning.current
    ) return
    liveCaseRefreshRunning.current = true
    try {
      const [caseResult, inviteResult, adjustmentResult, versionResult, safetyResult] =
        await Promise.all([
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
          apiRequest<CaseSafetyEventListResponse>(
            `/cases/safety-events/recent?case_id=${caseId}`,
            { staffToken: token },
          ),
        ])
      const visibleInvites = inviteResult.items.filter((item) => item.status !== 'revoked')
      const sessionResults = await Promise.all(
        visibleInvites
          .filter((item) => item.session_id)
          .map((item) =>
            apiRequest<PatientSession>(`/sessions/${item.session_id}`, {
              staffToken: token,
            }),
          ),
      )

      const nextAdjustmentIds = new Set(
        adjustmentResult.items.map((item) => item.request_id),
      )
      const knownAdjustments = knownAdjustmentIds.current
      if (
        knownAdjustments
        && adjustmentResult.items.some((item) => !knownAdjustments.has(item.request_id))
      ) {
        messageApi.info(t('收到新的患者调整建议'))
      }
      knownAdjustmentIds.current = nextAdjustmentIds

      const nextSafetyIds = new Set(safetyResult.items.map((item) => item.event_id))
      const knownSafetyIds = knownSafetyEventIds.current
      const newSafetyEvents = knownSafetyIds
        ? safetyResult.items.filter((item) => !knownSafetyIds.has(item.event_id))
        : []
      if (newSafetyEvents.length > 0) {
        const patientPaused = newSafetyEvents.some(
          (item) => item.event_type === 'patient_discomfort',
        )
        Modal.warning({
          title: t('患者安全提醒'),
          content: t(
            patientPaused
              ? '患者表示不适，会话已安全暂停，请立即关注。'
              : '系统拦截了一条包含敏感内容的患者调整建议，请及时关注。',
          ),
          okText: t('知道了'),
        })
      }
      knownSafetyEventIds.current = nextSafetyIds

      const nextSatisfiedSessionIds = new Set(
        sessionResults
          .filter((item) => item.patient_satisfied_version_id)
          .map((item) => item.session_id),
      )
      const knownSatisfiedSessions = knownSatisfiedSessionIds.current
      if (
        knownSatisfiedSessions
        && sessionResults.some(
          (item) =>
            item.patient_satisfied_version_id
            && !knownSatisfiedSessions.has(item.session_id),
        )
      ) {
        messageApi.success({
          content: t('患者满意当前图片'),
          duration: 3,
        })
      }
      knownSatisfiedSessionIds.current = nextSatisfiedSessionIds

      setClinicalCase(caseResult)
      setInvites(visibleInvites)
      setSessions(Object.fromEntries(sessionResults.map((item) => [item.session_id, item])))
      setAdjustments(adjustmentResult)
      setAvatarVersions(versionResult.items)
      setSafetyEvents(safetyResult.items)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
      }
    } finally {
      liveCaseRefreshRunning.current = false
    }
  }, [caseId, messageApi, navigate, t])

  useEffect(() => void loadCase(), [loadCase])

  useEffect(() => {
    const refreshVisibleCase = () => void loadLiveCase()
    const timer = window.setInterval(refreshVisibleCase, 2000)
    window.addEventListener('focus', refreshVisibleCase)
    document.addEventListener('visibilitychange', refreshVisibleCase)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refreshVisibleCase)
      document.removeEventListener('visibilitychange', refreshVisibleCase)
    }
  }, [loadLiveCase])

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
      messageApi.error(requestError instanceof Error ? requestError.message : t('邀请码创建失败'))
    } finally {
      setWorking(false)
    }
  }

  async function cancelInvite(target: SessionInvite) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<SessionInvite>(`/session-invites/${target.invite_id}`, {
        method: 'DELETE',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('invite-cancel'),
      })
      setCreatedInvite((current) =>
        current?.invite_id === target.invite_id ? null : current,
      )
      messageApi.success(t('邀请码已取消，患者将无法继续兑换'))
      await loadCase()
    } catch (requestError) {
      messageApi.error(
        requestError instanceof Error ? requestError.message : t('邀请码取消失败'),
      )
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
          ? {
              consent_confirmed: true,
              consent_version: 'v1',
              assessment_mode: target.has_prior_assessment
                ? assessmentMode
                : 'new_assessment',
            }
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
      setAssessmentMode(null)
      messageApi.success(t(action === 'start' ? '会话已启动' : action === 'resume' ? '会话已恢复' : '会话已结束'))
      void loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('操作失败'))
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
      messageApi.success(t('病例已归档，30 天删除倒计时已经开始'))
      void loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('归档失败'))
    } finally {
      setWorking(false)
    }
  }

  async function reviewAdjustment(
    target: DoctorAdjustment,
    decision: 'approve_as_is' | 'approve_edited' | 'reject',
    options?: {
      controlledInstruction?: string
      rejectionReason?: string
    },
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
          controlled_instruction:
            decision === 'approve_edited' ? options?.controlledInstruction : null,
          rejection_reason:
            decision === 'reject' ? options?.rejectionReason?.trim() : null,
        },
      })
      if (decision === 'approve_edited') {
        setAdjustTarget(null)
        setSelectedControlledInstruction('')
      }
      if (decision === 'reject') {
        setRejectTarget(null)
        setRejectionReason('')
      }
      messageApi.success(
        t(decision === 'reject' ? '已拒绝该调整建议' : '审核已保存，可以生成调整版本'),
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('审核未能保存'))
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
      messageApi.success(t('生图任务已提交，完成后需要医生审核才会展示给患者'))
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('生图任务提交失败'))
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
      messageApi.info(
        language === 'en'
          ? `Version ${target.generation_round} generation was cancelled`
          : `${t('第')} ${target.generation_round} ${t('版生成任务已取消')}`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('生成任务取消失败'))
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
      messageApi.success(t('调整版本已进入生图和安全检查流程'))
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('调整版本生成失败'))
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
          ? t('审核已通过；还需单独授权后患者才能查看')
          : t('该版本已拒绝并自动删除'),
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('版本审核失败'))
    } finally {
      setWorking(false)
    }
  }

  async function deleteAvatarVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest<DeleteAvatarVersionResponse>(`/avatar-versions/${target.version_id}/delete`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('avatar-version-delete'),
        body: {
          confirmation: 'DELETE_UNAUTHORIZED_AVATAR_VERSION',
          reason: 'doctor_manual_delete',
        },
      })
      messageApi.success(
        language === 'en'
          ? `Version ${target.generation_round} was permanently deleted`
          : `${t('第')} ${target.generation_round} ${t('版已永久删除')}`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('版本删除失败'))
    } finally {
      setWorking(false)
    }
  }

  async function authorizeVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning(t('请先启动本病例的患者监督会话'))
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
      messageApi.success(
        language === 'en'
          ? `Version ${target.generation_round} is now available to the patient`
          : `${t('已授权第')} ${target.generation_round} ${t('版，患者端现在可以查看')}`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('版本授权失败'))
    } finally {
      setWorking(false)
    }
  }

  async function rollbackVersion(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning(t('请先启动本病例的患者监督会话'))
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
        language === 'en'
          ? `Version ${target.generation_round} was selected for rollback. The previous authorization has been revoked; review and authorize it again.`
          : `${t('已选择第')} ${target.generation_round} ${t('版作为回退候选，旧授权已撤销；请重新审核后再授权')}`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('版本回退失败'))
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
      messageApi.success(t('指定版本和对应 Q1–Q8 快照已下载，操作已记录审计'))
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('版本下载失败'))
    } finally {
      setWorking(false)
    }
  }

  async function revokeAuthorization(target: AvatarVersion) {
    const token = staffTokenStore.get()
    if (!token || !caseId) return
    const activeSession = Object.values(sessions).find((item) => item.status === 'active')
    if (!activeSession) {
      messageApi.warning(t('没有可撤销授权的进行中监督会话'))
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
      messageApi.success(
        language === 'en'
          ? `Patient access to version ${target.generation_round} has been revoked`
          : `${t('已撤销第')} ${target.generation_round} ${t('版的患者展示授权')}`,
      )
      await loadCase()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('授权撤销失败'))
    } finally {
      setWorking(false)
    }
  }

  const generationRunning = avatarVersions.some((item) =>
    ['queued', 'generating', 'checking'].includes(item.generation_status),
  )
  const currentSession = invites
    .map((invite) => (invite.session_id ? sessions[invite.session_id] : null))
    .find((patientSession) =>
      patientSession
        ? !['ended', 'expired'].includes(patientSession.status)
        : false,
    )
  const flowInvite = invites[0] ?? null
  const flowSession =
    flowInvite?.session_id ? sessions[flowInvite.session_id] ?? null : null
  const flowStartedAt = flowSession?.started_at
    ? new Date(flowSession.started_at).getTime()
    : null
  const flowVersions = flowStartedAt === null
    ? []
    : avatarVersions.filter(
        (version) =>
          version.version_id === flowSession?.current_authorized_version_id
          || new Date(version.created_at).getTime() >= flowStartedAt,
      )
  const flowAdjustments = flowStartedAt === null
    ? []
    : (adjustments?.items ?? []).filter(
        (item) => new Date(item.submitted_at).getTime() >= flowStartedAt,
      )
  const flowGenerationRunning = flowVersions.some((item) =>
    ['queued', 'generating', 'checking'].includes(item.generation_status),
  )
  const hasRedeemedInvite = Boolean(flowSession)
  const hasStartedSession = Boolean(flowSession?.started_at)
  const hasConfirmedVisualDirection = Boolean(
    hasStartedSession
    && (
      flowSession?.assessment_mode === 'reuse_previous'
      || (
        visualFeatures?.is_doctor_confirmed
        && visualFeatures.confirmed_at
        && new Date(visualFeatures.confirmed_at).getTime() >= (flowStartedAt ?? 0)
      )
    ),
  )
  const hasGeneratedImage = flowVersions.some(
    (version) =>
      Boolean(version.image_url)
      || ['pending_doctor_review', 'approved', 'rejected'].includes(
        version.generation_status,
      ),
  )
  const hasReviewedImage = flowVersions.some((version) =>
    ['approved', 'rejected'].includes(version.generation_status),
  )
  const hasPatientFeedback = Boolean(
    flowAdjustments.length || flowSession?.patient_satisfied_version_id,
  )
  const hasPendingPatientFeedback = flowAdjustments.some(
    (item) => item.status === 'pending_doctor_review',
  )
  const hasOpenSession = Boolean(
    flowSession
    && ['waiting_doctor', 'active', 'paused'].includes(flowSession.status),
  )
  const hasEndedSession = flowSession?.status === 'ended'
  const caseArchived = clinicalCase?.status === 'archived'

  const baseCaseFlowSteps: CaseFlowStep[] = clinicalCase
    ? [
        {
          key: 'case-created',
          label: '病例已创建并归属当前医生',
          detail: '病例基础信息已建立',
          state: 'complete',
        },
        {
          key: 'invite-redeemed',
          label: '患者兑换一次性邀请码',
          detail: hasRedeemedInvite ? '患者已进入监督会话' : '等待患者兑换邀请码',
          state: hasRedeemedInvite ? 'complete' : 'pending',
        },
        {
          key: 'session-started',
          label: '医生确认当面知情同意并启动',
          detail: hasStartedSession ? '监督会话已经启动' : '等待医生启动监督会话',
          state: hasStartedSession ? 'complete' : 'pending',
        },
        {
          key: 'visual-direction',
          label: '记录声音体验并确认视觉表达方向',
          detail: hasConfirmedVisualDirection
            ? '声音记录与视觉方向已经确认'
            : '等待完成声音记录与视觉方向确认',
          state: hasConfirmedVisualDirection ? 'complete' : 'pending',
        },
        {
          key: 'image-generated',
          label: '已生成图片',
          detail: hasGeneratedImage
            ? '至少已有一个图像版本生成完成'
            : flowGenerationRunning
              ? '图像正在生成与安全检查中'
              : '等待生成首个图像版本',
          state: hasGeneratedImage ? 'complete' : 'pending',
        },
        {
          key: 'image-reviewed',
          label: '医生完成图片审核',
          detail: hasReviewedImage
            ? '至少已有一个图像版本完成医生审核'
            : flowVersions.some(
                (version) => version.generation_status === 'pending_doctor_review',
              )
              ? '已有图片等待医生审核'
              : '等待生成图片后进行审核',
          state: hasReviewedImage ? 'complete' : 'pending',
        },
        {
          key: 'patient-feedback',
          label: '患者修改意见',
          detail: hasPendingPatientFeedback
            ? '患者已提交修改意见，等待医生处理'
            : hasPatientFeedback
              ? '患者修改意见已处理或进入图像调整'
              : hasEndedSession || caseArchived
                ? '本次流程中患者未提交修改意见'
                : '等待患者查看图片并反馈',
          state: hasPendingPatientFeedback
            ? 'current'
            : hasPatientFeedback
              ? 'complete'
              : hasEndedSession || caseArchived
                ? 'skipped'
                : 'pending',
        },
        {
          key: 'session-ended',
          label: '会话结束',
          detail: hasOpenSession
            ? '当前仍有患者会话进行中'
            : hasEndedSession
              ? '患者会话已经结束'
              : '尚未产生需要结束的患者会话',
          state: hasEndedSession && !hasOpenSession
            ? 'complete'
            : !flowSession && caseArchived
              ? 'skipped'
              : 'pending',
        },
        {
          key: 'case-archived',
          label: '归档完成',
          detail: caseArchived
            ? '病例已归档并进入数据保留倒计时'
            : clinicalCase.status === 'completed'
              ? '病例已完成，可以进行归档'
              : '病例完成后可以归档',
          state: caseArchived ? 'complete' : 'pending',
        },
      ]
    : []

  const caseFlowSteps = caseArchived
    ? baseCaseFlowSteps.map((step) => ({
        ...step,
        state: step.state === 'pending' ? 'skipped' as const : step.state,
      }))
    : (() => {
        if (baseCaseFlowSteps.some((step) => step.state === 'current')) {
          return baseCaseFlowSteps
        }
        const currentIndex = baseCaseFlowSteps.findIndex(
          (step) => step.state === 'pending',
        )
        return baseCaseFlowSteps.map((step, index) => ({
          ...step,
          state: index === currentIndex ? 'current' as const : step.state,
        }))
      })()

  const latestSafetyEvent =
    currentSession?.status === 'paused'
      ? safetyEvents.find(
          (item) =>
            item.session_id === currentSession.session_id
            && item.event_type === 'patient_discomfort',
        ) ?? safetyEvents[0]
      : safetyEvents[0]

  if (loading) {
    return <div className="route-fallback"><Spin size="large" tip={t('正在加载病例…')} /></div>
  }

  return (
    <div className="case-page">
      {messageContext}
      <header className="case-page__header">
        <Brand />
        <div className="case-page__header-actions">
          <LanguageSwitcher />
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/doctor/workspace')}>
            {t('返回工作台')}
          </Button>
        </div>
      </header>
      <main className="case-page__content">
        {error && <Alert type="error" showIcon message={t('病例暂时不可用')} description={error} />}
        {clinicalCase && (
          <>
            <div className="case-page__title">
              <div>
                <span className="eyebrow">{t('去标识化病例')}</span>
                <h1>{clinicalCase.study_code}</h1>
                <p>{t('集中管理患者会话、声音访谈、视觉表达审核与后续反馈。')}</p>
              </div>
              <Space>
                <Tag color={clinicalCase.status === 'in_progress' ? 'processing' : 'default'}>
                  {t(clinicalCase.status === 'draft' ? '草稿' : clinicalCase.status === 'in_progress' ? '进行中' : clinicalCase.status === 'completed' ? '已完成' : '已归档')}
                </Tag>
                <Button
                  danger
                  disabled={clinicalCase.status === 'archived'}
                  onClick={() => setArchiveOpen(true)}
                >
                  {t('归档病例')}
                </Button>
              </Space>
            </div>

            {clinicalCase.retention_due_at && (
              <Alert
                type="warning"
                showIcon
                message={
                  clinicalCase.status === 'archived'
                    ? t('病例已归档')
                    : t('该病例已恢复，但永久删除倒计时仍在继续')
                }
                description={
                  language === 'en'
                    ? `Permanent deletion: ${new Date(clinicalCase.retention_due_at).toLocaleString(dateLocale)}. Restoring the case does not pause or reset the countdown, and prior patient sessions remain closed.`
                    : `${t('永久删除时间：')}${new Date(clinicalCase.retention_due_at).toLocaleString(dateLocale)}。${t('恢复不会暂停或重置倒计时，旧患者会话也不会恢复。')}`
                }
              />
            )}

            {latestSafetyEvent && (
              <Alert
                className="case-safety-alert"
                type={latestSafetyEvent.severity === 'critical' ? 'error' : 'warning'}
                showIcon
                message={t(
                  latestSafetyEvent.event_type === 'patient_discomfort'
                    ? '患者表示不适，请立即关注'
                    : '系统拦截了患者提交的敏感调整建议',
                )}
                description={`${new Date(latestSafetyEvent.created_at).toLocaleString(dateLocale)} · ${t(
                  latestSafetyEvent.event_type === 'patient_discomfort'
                    ? '会话已自动安全暂停，请先与患者确认状态，再由医生决定是否恢复。'
                    : '敏感内容未进入生图流程，原始敏感文本不会在提醒中展示。',
                )}`}
              />
            )}

            <div className="case-detail-grid">
              <Card title={t('患者会话与邀请码')} className="case-session-card" extra={<Button type="primary" icon={<KeyOutlined />} disabled={clinicalCase.status === 'archived'} loading={working} onClick={() => void createInvite()}>{t('创建邀请码')}</Button>}>
                {invites.length === 0 ? (
                  <Empty description={t('尚未创建邀请码')} />
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
                              <p>
                                {patientSession
                                  ? patientSession.started_at
                                    ? `${t('会话开始时间')} ${new Date(
                                        patientSession.started_at,
                                      ).toLocaleString(dateLocale)}`
                                    : t('患者已兑换，等待会话开始')
                                  : `${t('邀请码有效期至')} ${new Date(
                                      invite.expires_at,
                                    ).toLocaleString(dateLocale)}`}
                              </p>
                            </div>
                          </div>
                          <div className="invite-list__actions">
                            <Tag>{t(inviteLabels[invite.status])}</Tag>
                            {patientSession?.patient_satisfied_version_id && (
                              <Tag color="success" icon={<CheckCircleOutlined />}>
                                {t('已生成图片')}
                              </Tag>
                            )}
                            {invite.code && <Button type="text" icon={<CopyOutlined />} onClick={() => navigator.clipboard.writeText(invite.code!)}>{t('复制')}</Button>}
                            {invite.status === 'issued' && (
                              <Button
                                danger
                                type="text"
                                icon={<CloseOutlined />}
                                loading={working}
                                onClick={() =>
                                  Modal.confirm({
                                    title: t('取消这个邀请码？'),
                                    content: t('取消后，患者将无法使用该邀请码进入会话。'),
                                    okText: t('确认取消'),
                                    cancelText: t('返回'),
                                    okButtonProps: { danger: true },
                                    onOk: () => cancelInvite(invite),
                                  })
                                }
                              >
                                {t('取消邀请')}
                              </Button>
                            )}
                            {patientSession?.status === 'waiting_doctor' && (
                              <Button
                                type="primary"
                                icon={<PlayCircleOutlined />}
                                onClick={() => {
                                  setStartTarget(patientSession)
                                  setAssessmentMode(
                                    patientSession.has_prior_assessment
                                      ? null
                                      : 'new_assessment',
                                  )
                                }}
                              >
                                {t('确认并开始')}
                              </Button>
                            )}
                            {patientSession?.status === 'paused' && <Button type="primary" icon={<PlayCircleOutlined />} loading={working} onClick={() => void controlSession(patientSession, 'resume')}>{t('医生恢复')}</Button>}
                            {patientSession?.status === 'active'
                              && patientSession.assessment_mode === 'new_assessment' && (
                                <Button
                                  icon={<FormOutlined />}
                                  onClick={() =>
                                    navigate(
                                      `/doctor/cases/${caseId}/interview/${patientSession.session_id}`,
                                    )
                                  }
                                >
                                  {t('录入 Q1–Q8')}
                                </Button>
                              )}
                            {patientSession?.status === 'active'
                              && patientSession.assessment_mode === 'reuse_previous' && (
                                <Tag color="success">{t('沿用上次记录')}</Tag>
                              )}
                            {patientSession?.status === 'active' && <Button danger icon={<StopOutlined />} loading={working} onClick={() => void controlSession(patientSession, 'stop')}>{t('结束会话')}</Button>}
                          </div>
                          {patientSession && (
                            <div className="session-inline-status">
                              {patientSession.status === 'paused' ? <PauseCircleOutlined /> : <ClockCircleOutlined />}
                              <span>{t('会话状态：')}{t(sessionLabels[patientSession.status])}</span>
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </div>
                )}
              </Card>

              <Card title={t('当前流程')} className="case-flow-card">
                <Timeline
                  items={caseFlowSteps.map((step) => ({
                    color: step.state === 'complete' ? 'green' : 'gray',
                    dot: (
                      <span
                        className={`case-flow-dot case-flow-dot--${step.state}`}
                        aria-hidden="true"
                      />
                    ),
                    children: (
                      <div
                        className={`case-flow-step case-flow-step--${step.state}`}
                        data-step={step.key}
                        data-state={step.state}
                      >
                        <div className="case-flow-step__heading">
                          <strong>{t(step.label)}</strong>
                          <span className="case-flow-step__status">
                            {t(
                              step.state === 'complete'
                                ? '已完成'
                                : step.state === 'current'
                                  ? '当前步骤'
                                  : step.state === 'skipped'
                                    ? '未发生'
                                    : '待进行',
                            )}
                          </span>
                        </div>
                        <small>{t(step.detail)}</small>
                      </div>
                    ),
                  }))}
                />
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label={t('创建时间')}>{new Date(clinicalCase.created_at).toLocaleString(dateLocale)}</Descriptions.Item>
                  <Descriptions.Item label={t('累计会话')}>{clinicalCase.total_session_count}</Descriptions.Item>
                </Descriptions>
              </Card>
            </div>

            <Card
              className="avatar-generation-card"
              title={t('视觉表达生成与版本审核')}
              extra={
                <Space wrap>
                  <Tag color={visualFeatures?.is_doctor_confirmed ? 'success' : 'warning'}>
                    {t(visualFeatures?.is_doctor_confirmed ? '视觉特征已确认' : '等待确认视觉特征')}
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
                      ? t('当前版本生成中')
                      : avatarVersions.length
                        ? t('重新生成')
                        : t('生成首版 Avatar')}
                  </Button>
                </Space>
              }
            >
              {!visualFeatures?.is_doctor_confirmed && (
                <Alert
                  type="info"
                  showIcon
                  message={t('完成声音访谈并确认视觉表达方向后，才能生成图像')}
                />
              )}
              {avatarVersions.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('尚无生成版本')} />
              ) : (
                <div className="avatar-version-grid">
                  {avatarVersions.map((version) => (
                    <article className="avatar-version-card" key={version.version_id}>
                      <div className="avatar-version-card__preview">
                        {version.image_url ? (
                          <img src={version.image_url} alt={language === 'en' ? `Avatar version ${version.generation_round}` : `Avatar ${t('第')} ${version.generation_round} ${t('版')}`} />
                        ) : (
                          <div className="avatar-version-card__empty"><PictureOutlined /></div>
                        )}
                        <span>V{version.generation_round}</span>
                      </div>
                      <div className="avatar-version-card__body">
                        <div className="avatar-version-card__title">
                          <strong>{language === 'en' ? `Version ${version.generation_round}` : `${t('第')} ${version.generation_round} ${t('版')}`}</strong>
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
                            {t(generationStatusLabels[version.generation_status])}
                          </Tag>
                        </div>
                        <p>{t('依据医生确认的视觉方向生成')}</p>
                        {version.failure_code && <Alert type="warning" showIcon message={`${t('失败代码：')}${version.failure_code}`} />}
                        {clinicalCase.status !== 'archived'
                          && ['queued', 'generating', 'checking'].includes(version.generation_status) && (
                          <Button
                            danger
                            icon={<StopOutlined />}
                            loading={working}
                            onClick={() =>
                              Modal.confirm({
                                title: language === 'en' ? `Cancel generation of version ${version.generation_round}?` : `${t('取消第')} ${version.generation_round} ${t('版生成？')}`,
                                content: t('已经生成但尚未采用的临时图片会被丢弃，不影响此前已审核版本。'),
                                okText: t('确认取消'),
                                cancelText: t('继续生成'),
                                okButtonProps: { danger: true },
                                onOk: () => cancelGeneration(version),
                              })
                            }
                          >
                            {t('取消生成')}
                          </Button>
                        )}
                        {clinicalCase.status !== 'archived'
                          && version.generation_status === 'failed' && (
                          <Button
                            icon={<ReloadOutlined />}
                            loading={working}
                            disabled={generationRunning}
                            onClick={() => void generateAvatar('same_features_regenerate')}
                          >
                            {t('按相同特征重试')}
                          </Button>
                        )}
                        {clinicalCase.status !== 'archived'
                          && version.generation_status === 'pending_doctor_review' && (
                          <Space wrap>
                            <Button type="primary" icon={<SafetyCertificateOutlined />} loading={working} onClick={() => void reviewAvatar(version, 'approve')}>
                              {t('审核通过')}
                            </Button>
                            <Button danger icon={<CloseOutlined />} loading={working} onClick={() => void reviewAvatar(version, 'reject')}>
                              {t('拒绝此图')}
                            </Button>
                          </Space>
                        )}
                        {clinicalCase.status !== 'archived'
                          && version.generation_status === 'approved' && (
                          <Space wrap>
                            {version.is_authorized ? (
                              <>
                                <Tag color="success" icon={<CheckCircleOutlined />}>{t('患者当前可见')}</Tag>
                                <Button
                                  danger
                                  icon={<StopOutlined />}
                                  loading={working}
                                  onClick={() => void revokeAuthorization(version)}
                                >
                                  {t('撤销患者授权')}
                                </Button>
                              </>
                            ) : version.is_current_candidate ? (
                              <Button type="primary" icon={<CheckCircleOutlined />} loading={working} onClick={() => void authorizeVersion(version)}>
                                {t('授权患者查看')}
                              </Button>
                            ) : (
                              <Button
                                icon={<HistoryOutlined />}
                                loading={working}
                                onClick={() =>
                                  Modal.confirm({
                                    title: language === 'en' ? `Roll back to version ${version.generation_round}?` : `${t('回退到第')} ${version.generation_round} ${t('版？')}`,
                                    content: t('当前患者授权将立即撤销。该历史版本必须重新审核并再次授权后，患者才能查看。'),
                                    okText: t('确认回退'),
                                    cancelText: t('取消'),
                                    okButtonProps: { danger: true },
                                    onOk: () => rollbackVersion(version),
                                  })
                                }
                              >
                                {t('选择此版回退')}
                              </Button>
                            )}
                          </Space>
                        )}
                        {version.snapshot_available
                          && version.image_url
                          && (
                            clinicalCase.status === 'archived'
                            || version.generation_status === 'approved'
                          ) && (
                          <Button icon={<DownloadOutlined />} loading={working} onClick={() => void downloadVersion(version)}>
                            {t('下载此版')}
                          </Button>
                        )}
                        {['approved', 'rejected', 'failed', 'cancelled'].includes(version.generation_status) && (
                          <Button
                            danger
                            icon={<DeleteOutlined />}
                            loading={working}
                            disabled={clinicalCase.status !== 'archived' && version.is_authorized}
                            title={
                              clinicalCase.status !== 'archived' && version.is_authorized
                                ? t('患者当前正在查看，不能删除')
                                : undefined
                            }
                            onClick={() =>
                              Modal.confirm({
                                title: language === 'en'
                                  ? `Permanently delete version ${version.generation_round}?`
                                  : `${t('永久删除第')} ${version.generation_round} ${t('版？')}`,
                                content: t('删除后无法恢复。'),
                                okText: t('确认永久删除'),
                                cancelText: t('取消'),
                                okButtonProps: { danger: true },
                                onOk: () => deleteAvatarVersion(version),
                              })
                            }
                          >
                            {clinicalCase.status !== 'archived' && version.is_authorized
                              ? t('患者查看中，禁止删除')
                              : t('删除图像')}
                          </Button>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </Card>

            <Card
              className="doctor-adjustment-card"
              title={t('患者反馈与图像调整')}
              extra={<Tag>{flowAdjustments.length} / 3 {t('次额度已使用')}</Tag>}
            >
              {!adjustments || adjustments.items.length === 0 ? (
                <Empty description={t('患者尚未提交调整建议')} />
              ) : (
                <div className="doctor-adjustment-list">
                  {adjustments.items.map((item) => (
                    <article key={item.request_id}>
                      <div className="doctor-adjustment-list__meta">
                        <span>
                          {language === 'en' ? `Request ${item.sequence_no}` : `${t('第')} ${item.sequence_no} ${t('次')}`} · {new Date(item.submitted_at).toLocaleString(dateLocale)}
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
                          {t(adjustmentStatusLabels[item.status])}
                        </Tag>
                      </div>
                      <blockquote>{item.instruction}</blockquote>
                      {item.controlled_instruction && (
                        <div className="controlled-instruction">
                          <SafetyCertificateOutlined /> {t('受控指令：')}
                          {localizeControlledInstruction(
                            item.controlled_instruction,
                            t,
                            language,
                          )}
                        </div>
                      )}
                      {item.status === 'pending_doctor_review' && (
                        <div className="controlled-instruction controlled-instruction--suggested">
                          <SafetyCertificateOutlined /> {t('系统建议受控指令：')}
                          {localizeControlledInstruction(
                            item.suggested_controlled_instruction,
                            t,
                            language,
                          )}
                        </div>
                      )}
                      {item.status === 'rejected' && item.rejection_reason && (
                        <Alert
                          type="info"
                          showIcon
                          message={t('拒绝理由')}
                          description={item.rejection_reason}
                        />
                      )}
                      {item.status === 'pending_doctor_review' && (
                        <Space wrap>
                          <Button
                            type="primary"
                            icon={<CheckCircleOutlined />}
                            loading={working}
                            onClick={() => void reviewAdjustment(item, 'approve_as_is')}
                          >
                            {t('接受系统研判')}
                          </Button>
                          <Button
                            icon={<FormOutlined />}
                            loading={working}
                            onClick={() => {
                              setAdjustTarget(item)
                              setSelectedControlledInstruction(
                                item.suggested_controlled_instruction,
                              )
                            }}
                          >
                            {t('医生调整')}
                          </Button>
                          <Button
                            danger
                            icon={<CloseOutlined />}
                            loading={working}
                            onClick={() => {
                              setRejectTarget(item)
                              setRejectionReason('')
                            }}
                          >
                            {t('拒绝')}
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
                          {t('生成受控调整版本')}
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

      <Modal
        title={t('确认已完成当面知情同意')}
        open={Boolean(startTarget)}
        onCancel={() => {
          setStartTarget(null)
          setConsentConfirmed(false)
          setAssessmentMode(null)
        }}
        okText={t('确认并启动会话')}
        cancelText={t('取消')}
        okButtonProps={{
          disabled:
            !consentConfirmed
            || (Boolean(startTarget?.has_prior_assessment) && !assessmentMode),
          loading: working,
        }}
        onOk={() => startTarget && void controlSession(startTarget, 'start')}
      >
        <Alert type="info" showIcon icon={<SafetyCertificateOutlined />} message={t('该确认由当前医生完成')} description={t('系统只保存确认医生、确认时间和同意文本版本，不要求患者在线签名。')} />
        {startTarget?.has_prior_assessment ? (
          <div className="session-assessment-choice">
            <strong>{t('选择本次会话的评估方式')}</strong>
            <Radio.Group
              value={assessmentMode}
              onChange={(event) => setAssessmentMode(event.target.value)}
            >
              <Radio value="reuse_previous">
                <span>
                  <strong>{t('沿用上次记录，继续本次会话')}</strong>
                  <small>
                    {t('保留上次完整的 Q1–Q8 与视觉方向，直接继续查看和讨论。')}
                  </small>
                </span>
              </Radio>
              <Radio value="new_assessment">
                <span>
                  <strong>{t('重新评估 Q1–Q8')}</strong>
                  <small>
                    {t('为本次会话建立一份新记录，既往记录和图像不会被覆盖。')}
                  </small>
                </span>
              </Radio>
            </Radio.Group>
          </div>
        ) : (
          <Alert
            className="session-first-assessment"
            type="success"
            showIcon
            message={t('首次会话需要完成 Q1–Q8')}
            description={t('完成后，这份记录可在后续会话中沿用。')}
          />
        )}
        <Checkbox className="consent-check" checked={consentConfirmed} onChange={(event) => setConsentConfirmed(event.target.checked)}>
          {t('我已在现场向患者说明研究用途、展示边界和安全暂停方式，并确认其同意继续。')}
        </Checkbox>
      </Modal>

      <Modal
        title={t('调整患者描述')}
        open={Boolean(adjustTarget)}
        okText={t('确认调整并接受')}
        cancelText={t('取消')}
        okButtonProps={{
          disabled: !selectedControlledInstruction,
          loading: working,
        }}
        onCancel={() => {
          setAdjustTarget(null)
          setSelectedControlledInstruction('')
        }}
        onOk={() => {
          if (adjustTarget && selectedControlledInstruction) {
            void reviewAdjustment(adjustTarget, 'approve_edited', {
              controlledInstruction: selectedControlledInstruction,
            })
          }
        }}
      >
        <Alert
          type="info"
          showIcon
          message={t('保留患者原话，由医生选择更准确的受控表达')}
          description={t('患者原始描述不会被覆盖；后续生图只使用医生确认后的低刺激受控指令。')}
        />
        <div className="doctor-adjustment-modal__original">
          <strong>{t('患者原始描述')}</strong>
          <blockquote>{adjustTarget?.instruction}</blockquote>
        </div>
        <Radio.Group
          className="doctor-adjustment-options"
          value={selectedControlledInstruction}
          onChange={(event) => setSelectedControlledInstruction(event.target.value)}
        >
          {adjustTarget?.controlled_options.map((option) => (
            <Radio key={option} value={option}>
              {localizeControlledInstruction(option, t, language)}
            </Radio>
          ))}
        </Radio.Group>
      </Modal>

      <Modal
        title={t('填写拒绝理由')}
        open={Boolean(rejectTarget)}
        okText={t('确认拒绝')}
        cancelText={t('取消')}
        okButtonProps={{
          danger: true,
          disabled: rejectionReason.trim().length < 2,
          loading: working,
        }}
        onCancel={() => {
          setRejectTarget(null)
          setRejectionReason('')
        }}
        onOk={() => {
          if (rejectTarget) {
            void reviewAdjustment(rejectTarget, 'reject', {
              rejectionReason,
            })
          }
        }}
      >
        <Alert
          type="info"
          showIcon
          message={t('请用简短、清晰且适合患者阅读的语言说明原因')}
          description={t('患者端会显示该理由；请勿填写诊断结论或不必要的身份信息。')}
        />
        <Input.TextArea
          aria-label={t('拒绝理由')}
          value={rejectionReason}
          onChange={(event) => setRejectionReason(event.target.value)}
          placeholder={t('例如：本次建议与已确认的低刺激视觉方向不一致，请在现场与医生进一步讨论。')}
          autoSize={{ minRows: 4, maxRows: 7 }}
          maxLength={300}
          showCount
        />
      </Modal>

      <Modal title={t('归档病例')} open={archiveOpen} onCancel={() => setArchiveOpen(false)} okText={t('确认归档')} cancelText={t('取消')} okButtonProps={{ danger: true, loading: working }} onOk={() => void archiveCase()}>
        <p>{t('归档会立即结束所有患者会话，并从现在起启动 30 天永久删除倒计时。')}</p>
      </Modal>

      <Modal title={t('一次性患者邀请码')} open={Boolean(createdInvite)} onCancel={() => setCreatedInvite(null)} footer={<Button type="primary" onClick={() => setCreatedInvite(null)}>{t('完成')}</Button>}>
        <Alert type="success" showIcon message={t('邀请码已创建')} description={t('仅在现场监督会话中提供；兑换后不能再次使用。')} />
        <div className="invite-code-display">{createdInvite?.code}</div>
        <Button block icon={<CopyOutlined />} onClick={() => createdInvite?.code && navigator.clipboard.writeText(createdInvite.code)}>{t('复制邀请码')}</Button>
      </Modal>
    </div>
  )
}
