const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiClientError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  staffToken?: string | null
  patientToken?: string | null
  idempotencyKey?: string
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' })
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  if (options.staffToken) headers.set('Authorization', `Bearer ${options.staffToken}`)
  if (options.patientToken) headers.set('X-Session-Token', options.patientToken)
  if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey)

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = payload?.error
    throw new ApiClientError(
      response.status,
      error?.code ?? 'REQUEST_FAILED',
      error?.message ?? '请求未能完成，请稍后重试',
    )
  }
  return payload as T
}

export async function downloadApiFile(
  path: string,
  staffToken: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: 'application/zip',
      Authorization: `Bearer ${staffToken}`,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = payload?.error
    throw new ApiClientError(
      response.status,
      error?.code ?? 'DOWNLOAD_FAILED',
      error?.message ?? '下载未能完成，请稍后重试',
    )
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename =
    disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? 'avatar-version.zip'
  return { blob: await response.blob(), filename }
}

export function newIdempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

export const staffTokenStore = {
  get: () => sessionStorage.getItem('avatar.staff_token'),
  set: (value: string) => sessionStorage.setItem('avatar.staff_token', value),
  clear: () => sessionStorage.removeItem('avatar.staff_token'),
}

export function getOrCreateDeviceBinding(): string {
  const key = 'avatar.patient_device_binding'
  const existing = localStorage.getItem(key)
  if (existing) return existing
  const created = `device-${crypto.randomUUID()}`
  localStorage.setItem(key, created)
  return created
}

export function setPatientSession(sessionId: string, token: string): void {
  sessionStorage.setItem(`avatar.patient_session.${sessionId}`, token)
}

export function getPatientSessionToken(sessionId: string): string | null {
  return sessionStorage.getItem(`avatar.patient_session.${sessionId}`)
}

export function clearPatientSession(sessionId: string): void {
  sessionStorage.removeItem(`avatar.patient_session.${sessionId}`)
}

export type StaffUser = {
  user_id: string
  role: 'doctor' | 'admin'
  display_name: string
  email: string
}

export type LoginResponse = {
  access_token: string
  token_type: 'Bearer'
  expires_at: string
  user: StaffUser
}

export type DoctorApplicationResponse = {
  status: 'verification_required'
  message: string
  development_verification_token: string | null
}

export type VerifyEmailResponse = {
  status: 'verified'
  approval_status: 'pending' | 'approved' | 'rejected'
  message: string
}

export type ClinicalCase = {
  case_id: string
  study_code: string
  status: 'draft' | 'in_progress' | 'completed' | 'archived'
  created_at: string
  updated_at: string
  archived_at: string | null
  retention_due_at: string | null
  active_session_count: number
  total_session_count: number
}

export type CaseListResponse = {
  items: ClinicalCase[]
  page: number
  page_size: number
  total: number
}

export type CaseSafetyEvent = {
  event_id: number
  case_id: string
  study_code: string
  session_id: string | null
  event_type: 'patient_discomfort' | 'sensitive_adjustment'
  severity: 'warning' | 'critical'
  risk_rule_codes: string[]
  created_at: string
}

export type CaseSafetyEventListResponse = {
  items: CaseSafetyEvent[]
}

export type SessionInvite = {
  invite_id: string
  session_id: string | null
  code: string | null
  code_mask: string
  status: 'issued' | 'redeemed_waiting' | 'active' | 'ended' | 'revoked' | 'expired'
  created_at: string
  expires_at: string
}

export type InviteListResponse = { items: SessionInvite[] }

export type PatientSession = {
  session_id: string
  case_id: string
  study_code: string | null
  status: 'waiting_doctor' | 'active' | 'paused' | 'ended' | 'expired'
  stage: string
  assessment_mode: 'new_assessment' | 'reuse_previous'
  has_prior_assessment: boolean
  current_authorized_version_id: string | null
  patient_satisfied_version_id: string | null
  patient_satisfied_at: string | null
  adjustments: { used: number; limit: number; has_pending: boolean }
  created_at: string
  started_at: string | null
  paused_at: string | null
  ended_at: string | null
  expires_at: string
}

export type VoiceFeatureContract = {
  question_order: string[]
  enums: Record<string, string[]>
  optional_nullable_questions: string[]
  emotion_max_length: 6
  visual_feature_keys: string[]
  controlled_visual_options: Record<string, string[]>
  initial_risk_classification: false
}

export type VoiceFeatures = {
  sound_description_id: string | null
  case_id: string
  session_id: string | null
  answers: Record<string, unknown>
  answered_questions: string[]
  completed_count: number
  total_count: 8
  complete: boolean
  updated_at: string | null
}

export type VisualFeatures = {
  visual_feature_id: string
  case_id: string
  source_sound_description_id: string
  system_result: Record<string, string>
  doctor_edited: Record<string, string> | null
  effective_features: Record<string, string>
  controlled_options: Record<string, string[]>
  mapping_explanation: {
    effective_power_level: number
    effective_malice_level: number
    safety_rules_applied: string[]
    initial_risk_classification_performed: false
  }
  mapping_version: string
  is_doctor_confirmed: boolean
  confirmed_at: string | null
  updated_at: string
}

export type AdjustmentStatus =
  | 'pending_doctor_review'
  | 'approved_as_is'
  | 'approved_edited'
  | 'rejected'
  | 'generating'
  | 'applied'
  | 'generation_failed'
  | 'cancelled'

export type PatientAdjustment = {
  request_id: string
  sequence_no: number
  instruction: string
  status: AdjustmentStatus
  rejection_reason: string | null
  submitted_at: string
  reviewed_at: string | null
}

export type PatientAdjustmentList = {
  items: PatientAdjustment[]
  used: number
  limit: 3
  has_pending: boolean
}

export type SubmitAdjustmentResponse = PatientAdjustment & {
  used: number
  limit: 3
  patient_message: string
}

export type DoctorAdjustment = PatientAdjustment & {
  controlled_instruction: string | null
  suggested_controlled_instruction: string
  controlled_options: string[]
}

export type DoctorAdjustmentList = {
  items: DoctorAdjustment[]
  used: number
  limit: 3
  has_pending: boolean
  controlled_options: string[]
}

export type PatientAvatar = {
  version_id: string
  authorization_status: 'authorized'
  display_mode: 'image' | 'mock_placeholder'
  image_url: string | null
  message: string | null
}

export type GenerationMode =
  | 'initial'
  | 'same_features_regenerate'
  | 'feature_update'
  | 'patient_adjustment'

export type GenerationStatus =
  | 'queued'
  | 'generating'
  | 'checking'
  | 'pending_doctor_review'
  | 'approved'
  | 'rejected'
  | 'failed'
  | 'cancelled'

export type AvatarVersion = {
  version_id: string
  case_id: string
  generation_round: number
  generation_mode: GenerationMode
  generation_status: GenerationStatus
  safety_status: string
  doctor_review_status: string
  provider_kind: string
  provider_model: string
  prompt_template_version: string
  image_url: string | null
  failure_code: string | null
  is_current_candidate: boolean
  is_authorized: boolean
  snapshot_available: boolean
  doctor_reviewed_at: string | null
  source_adjustment_request_id: string | null
  created_at: string
  completed_at: string | null
}

export type AvatarVersionList = { items: AvatarVersion[] }

export type DeleteAvatarVersionResponse = {
  version_id: string
  generation_round: number
  deleted: true
}

export type AdminDoctor = {
  user_id: string
  email: string
  display_name: string
  email_verified: boolean
  approval_status: 'pending' | 'approved' | 'rejected'
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export type AdminDoctorList = { items: AdminDoctor[]; total: number }

export type AdminRiskRule = {
  rule_id: string
  rule_code: string
  category: string
  rule_type: 'direct' | 'context' | 'pii'
  trigger_terms: string[]
  context_terms: string[] | null
  exclusion_terms: string[] | null
  patient_message_type: 'risk' | 'identity' | 'crisis'
  version: string
  is_enabled: boolean
  updated_at: string
}

export type AdminRiskRuleList = { items: AdminRiskRule[] }

export type AdminStats = {
  doctors: Record<string, number>
  cases: Record<string, number>
  sessions: Record<string, number>
  adjustments: Record<string, number>
  risk_blocks: number
  retention_jobs: Record<string, number>
  generations: Record<string, number>
  generation_success_rate: number | null
  average_generation_seconds: number | null
  alerts: {
    code: string
    severity: 'info' | 'warning' | 'critical'
    message: string
    count: number
  }[]
}

export type AdminAuditEvent = {
  audit_id: number
  actor_type: 'doctor' | 'admin' | 'patient' | 'system'
  actor_user_id: string | null
  action: string
  result: 'success' | 'failed' | 'blocked'
  metadata: Record<string, unknown> | null
  created_at: string
}

export type AdminAuditList = {
  items: AdminAuditEvent[]
  page: number
  page_size: number
  total: number
}

export type AdminArchivedCase = {
  case_id: string
  study_code: string
  archived_at: string
  retention_due_at: string
  restorable: boolean
}

export type AdminArchivedCaseList = { items: AdminArchivedCase[] }

export type DeleteArchivedCaseResponse = {
  case_id: string
  retention_job_id: string
  status: 'scheduled' | 'running'
}

export type RetentionJob = {
  retention_job_id: string
  status: 'scheduled' | 'running' | 'retrying' | 'completed' | 'failed'
  retention_started_at: string
  retention_due_at: string
  attempt_count: number
  last_attempt_at: string | null
  deleted_categories: Record<string, unknown> | null
  last_error_code: string | null
  completed_at: string | null
}

export type RetentionJobList = { items: RetentionJob[] }
