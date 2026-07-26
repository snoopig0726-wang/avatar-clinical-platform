import {
  AuditOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  LogoutOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  type AdminArchivedCase,
  type AdminArchivedCaseList,
  type AdminAuditEvent,
  type AdminAuditList,
  type AdminDoctor,
  type AdminDoctorList,
  type AdminRiskRule,
  type AdminRiskRuleList,
  type AdminStats,
  newIdempotencyKey,
  type RetentionJobList,
  staffTokenStore,
} from '../lib/api'

type RuleFormValues = {
  category: string
  trigger_terms: string
  context_terms: string
  exclusion_terms: string
  version: string
  is_enabled: boolean
}

const approvalLabels = {
  pending: { text: '待审批', color: 'gold' },
  approved: { text: '已批准', color: 'green' },
  rejected: { text: '已拒绝', color: 'default' },
}

const ruleTypeLabels: Record<AdminRiskRule['rule_type'], string> = {
  direct: '直接匹配',
  context: '结合上下文',
  pii: '身份信息',
}

const actorLabels: Record<AdminAuditEvent['actor_type'], string> = {
  admin: '管理员',
  doctor: '医生',
  patient: '患者',
  system: '系统',
}

const resultLabels: Record<AdminAuditEvent['result'], { text: string; color: string }> = {
  success: { text: '成功', color: 'green' },
  blocked: { text: '已拦截', color: 'orange' },
  failed: { text: '失败', color: 'red' },
}

const auditActionLabels: Record<string, string> = {
  'admin.doctor_access_updated': '医护账号权限已更新',
  'admin.risk_rule_updated': '安全规则已更新',
  'admin.case_restored': '归档病例已恢复',
  'admin.case_deletion_scheduled': '病例永久删除已提交',
  'doctor.application_submitted': '医护账号申请已提交',
  'doctor.email_verified': '医护邮箱已验证',
  'case.created': '病例已创建',
  'case.archived': '病例已归档',
  'invite.created': '患者邀请码已创建',
  'invite.revoked': '患者邀请码已取消',
  'invite.redeemed': '患者邀请码已兑换',
  'session.started': '患者会话已开始',
  'session.safety_paused': '患者会话因安全原因暂停',
  'session.resumed': '患者会话已恢复',
  'session.ended': '患者会话已结束',
  'voice_feature.saved': '声音访谈记录已保存',
  'visual_features.extracted': '视觉特征已提取',
  'visual_features.confirmed': '视觉特征已确认',
  'avatar.generation_requested': 'Avatar 生成已提交',
  'avatar.generation_cancelled': 'Avatar 生成已取消',
  'avatar.downloaded': 'Avatar 图像已下载',
  'avatar.reviewed': 'Avatar 版本已审核',
  'avatar.version_deleted': 'Avatar 图像版本已删除',
  'avatar.rollback_requested': 'Avatar 版本回退已提交',
  'avatar.authorized': 'Avatar 版本已授权患者查看',
  'avatar.authorization_revoked': 'Avatar 患者授权已撤销',
  'adjustment.submitted': '患者调整建议已提交',
  'adjustment.reviewed': '患者调整建议已审核',
  'adjustment.risk_blocked': '患者调整建议已被安全规则拦截',
  'avatar.adjustment_generation_requested': '调整版 Avatar 生成已提交',
  'retention.case_permanently_deleted': '归档病例已永久删除',
}

const operationalAlertLabels: Record<string, string> = {
  RETENTION_FAILED: '存在永久删除失败任务，需要检查后台服务。',
  RETENTION_OVERDUE: '存在已到删除时间但尚未完成删除的病例。',
  GENERATION_STUCK: '存在超过 15 分钟仍未完成的生图任务。',
  GENERATION_FAILED_24H: '过去 24 小时存在生图失败任务。',
}

const auditSourceLabels: Record<string, string> = {
  risk_interception: '安全规则自动拦截',
  admin_manual_delete: '管理员手动删除',
  doctor_manual_delete: '医生手动删除',
}

function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean))]
}

export function AdminDashboardPage() {
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const [messageApi, messageContext] = message.useMessage()
  const [ruleForm] = Form.useForm<RuleFormValues>()
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [doctors, setDoctors] = useState<AdminDoctor[]>([])
  const [rules, setRules] = useState<AdminRiskRule[]>([])
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [audits, setAudits] = useState<AdminAuditList | null>(null)
  const [archivedCases, setArchivedCases] = useState<AdminArchivedCase[]>([])
  const [retentionJobs, setRetentionJobs] = useState<RetentionJobList['items']>([])
  const [editingRule, setEditingRule] = useState<AdminRiskRule | null>(null)
  const [accountSearch, setAccountSearch] = useState('')
  const [accountApproval, setAccountApproval] = useState('all')
  const [accountStatus, setAccountStatus] = useState('all')
  const [ruleSearch, setRuleSearch] = useState('')
  const [ruleStatus, setRuleStatus] = useState('all')
  const [auditSearch, setAuditSearch] = useState('')
  const [auditActor, setAuditActor] = useState('all')
  const [auditResult, setAuditResult] = useState('all')
  const [retentionSearch, setRetentionSearch] = useState('')

  const loadDashboard = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token) {
      navigate('/admin/login', { replace: true })
      return
    }
    try {
      const [doctorData, ruleData, statsData, auditData, archivedData, retentionData] =
        await Promise.all([
          apiRequest<AdminDoctorList>('/admin/doctors', { staffToken: token }),
          apiRequest<AdminRiskRuleList>('/admin/risk-rules', { staffToken: token }),
          apiRequest<AdminStats>('/admin/stats', { staffToken: token }),
          apiRequest<AdminAuditList>('/admin/audit-logs?page_size=50', { staffToken: token }),
          apiRequest<AdminArchivedCaseList>('/admin/archived-cases', { staffToken: token }),
          apiRequest<RetentionJobList>('/admin/retention-jobs', { staffToken: token }),
        ])
      setDoctors(doctorData.items)
      setRules(ruleData.items)
      setStats(statsData)
      setAudits(auditData)
      setArchivedCases(archivedData.items)
      setRetentionJobs(retentionData.items)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/admin/login', { replace: true })
        return
      }
      setError(requestError instanceof Error ? requestError.message : t('管理后台暂时无法加载'))
    } finally {
      setLoading(false)
    }
  }, [navigate, t])

  useEffect(() => void loadDashboard(), [loadDashboard])

  const hasActiveDeletion = retentionJobs.some((job) => {
    if (job.status === 'running' || job.status === 'retrying') return true
    return job.status === 'scheduled' && new Date(job.retention_due_at).getTime() <= Date.now()
  })

  useEffect(() => {
    if (!hasActiveDeletion) return
    const intervalId = window.setInterval(() => void loadDashboard(), 2500)
    return () => window.clearInterval(intervalId)
  }, [hasActiveDeletion, loadDashboard])

  const filteredDoctors = useMemo(() => {
    const query = accountSearch.trim().toLocaleLowerCase()
    return doctors.filter((doctor) => {
      const matchesSearch = !query
        || doctor.display_name.toLocaleLowerCase().includes(query)
        || doctor.email.toLocaleLowerCase().includes(query)
      const matchesApproval = accountApproval === 'all' || doctor.approval_status === accountApproval
      const matchesStatus = accountStatus === 'all'
        || (accountStatus === 'enabled' ? doctor.is_active : !doctor.is_active)
      return matchesSearch && matchesApproval && matchesStatus
    })
  }, [accountApproval, accountSearch, accountStatus, doctors])

  const filteredRules = useMemo(() => {
    const query = ruleSearch.trim().toLocaleLowerCase()
    return rules.filter((rule) => {
      const matchesSearch = !query
        || rule.rule_code.toLocaleLowerCase().includes(query)
        || rule.category.toLocaleLowerCase().includes(query)
      const matchesStatus = ruleStatus === 'all'
        || (ruleStatus === 'enabled' ? rule.is_enabled : !rule.is_enabled)
      return matchesSearch && matchesStatus
    })
  }, [ruleSearch, ruleStatus, rules])

  const filteredAudits = useMemo(() => {
    const query = auditSearch.trim().toLocaleLowerCase()
    return (audits?.items ?? []).filter((audit) => {
      const actionLabel = t(auditActionLabels[audit.action] ?? audit.action).toLocaleLowerCase()
      const actorLabel = t(actorLabels[audit.actor_type]).toLocaleLowerCase()
      const matchesSearch = !query
        || actionLabel.includes(query)
        || actorLabel.includes(query)
        || audit.action.toLocaleLowerCase().includes(query)
      const matchesActor = auditActor === 'all' || audit.actor_type === auditActor
      const matchesResult = auditResult === 'all' || audit.result === auditResult
      return matchesSearch && matchesActor && matchesResult
    })
  }, [auditActor, auditResult, auditSearch, audits, t])

  const filteredArchivedCases = useMemo(() => {
    const query = retentionSearch.trim().toLocaleLowerCase()
    return archivedCases.filter((item) => !query || item.study_code.toLocaleLowerCase().includes(query))
  }, [archivedCases, retentionSearch])

  function describeAuditMetadata(metadata: Record<string, unknown> | null): string {
    if (!metadata) return '—'
    const summaries: string[] = []
    const deletedCategories = metadata.deleted_categories
    if (deletedCategories && typeof deletedCategories === 'object') {
      const total = Object.values(deletedCategories).reduce<number>(
        (sum, value) => sum + (typeof value === 'number' ? value : 0),
        0,
      )
      summaries.push(`${t('已删除关联记录')} ${total} ${t('条')}`)
    }
    const changedFields = metadata.changed_fields
    if (Array.isArray(changedFields)) {
      const fieldLabels: Record<string, string> = {
        approval_status: t('审批状态'),
        is_active: t('账号状态'),
        category: t('风险类别'),
        version: t('规则版本'),
        is_enabled: t('启用状态'),
      }
      summaries.push(`${t('变更')}：${changedFields.map((field) => fieldLabels[String(field)] ?? String(field)).join('、')}`)
    }
    if (typeof metadata.consent_version === 'string') {
      summaries.push(`${t('知情同意版本')}：${metadata.consent_version}`)
    }
    if (metadata.reason_present === true) summaries.push(t('已记录操作原因'))
    if (typeof metadata.source === 'string') {
      summaries.push(`${t('操作来源')}：${t(auditSourceLabels[metadata.source] ?? '系统流程')}`)
    }
    return summaries.length > 0 ? summaries.join(' · ') : t('已记录必要的脱敏操作信息')
  }

  async function updateDoctor(doctor: AdminDoctor, body: Record<string, unknown>) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest(`/admin/doctors/${doctor.user_id}`, {
        method: 'PATCH',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('admin-doctor-access'),
        body,
      })
      messageApi.success(t('医生账户权限已更新'))
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('账户更新失败'))
    } finally {
      setWorking(false)
    }
  }

  function openRuleEditor(rule: AdminRiskRule) {
    setEditingRule(rule)
    ruleForm.setFieldsValue({
      category: rule.category,
      trigger_terms: rule.trigger_terms.join('\n'),
      context_terms: (rule.context_terms ?? []).join('\n'),
      exclusion_terms: (rule.exclusion_terms ?? []).join('\n'),
      version: rule.version,
      is_enabled: rule.is_enabled,
    })
  }

  async function saveRule(values: RuleFormValues) {
    const token = staffTokenStore.get()
    if (!token || !editingRule) return
    setWorking(true)
    try {
      await apiRequest(`/admin/risk-rules/${editingRule.rule_id}`, {
        method: 'PUT',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('admin-risk-rule'),
        body: {
          category: values.category,
          trigger_terms: splitTerms(values.trigger_terms),
          context_terms: splitTerms(values.context_terms),
          exclusion_terms: splitTerms(values.exclusion_terms),
          version: values.version,
          is_enabled: values.is_enabled,
        },
      })
      messageApi.success(t('风险规则已更新，只影响新的患者请求'))
      setEditingRule(null)
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('规则更新失败'))
    } finally {
      setWorking(false)
    }
  }

  async function restoreCase(item: AdminArchivedCase) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest(`/admin/cases/${item.case_id}/restore`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('admin-case-restore'),
        body: { reason: 'admin_approved_restore' },
      })
      messageApi.success(t('病例已恢复为草稿；原30天删除时间保持不变'))
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('病例恢复失败'))
    } finally {
      setWorking(false)
    }
  }

  async function permanentlyDeleteCase(item: AdminArchivedCase) {
    const token = staffTokenStore.get()
    if (!token) return
    setWorking(true)
    try {
      await apiRequest(`/admin/cases/${item.case_id}/permanent-delete`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('admin-case-permanent-delete'),
        body: {
          confirmation: 'PERMANENTLY_DELETE_ARCHIVED_CASE',
          reason: 'admin_confirmed_immediate_deletion',
        },
      })
      messageApi.success(t('永久删除任务已提交，系统正在后台处理'))
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('病例永久删除失败'))
    } finally {
      setWorking(false)
    }
  }

  function confirmPermanentDelete(item: AdminArchivedCase) {
    Modal.confirm({
      title: t('永久删除这个归档病例？'),
      icon: <DeleteOutlined />,
      content: (
        <div className="admin-permanent-delete-confirm">
          <p>{t('此操作会立即删除病例、患者会话、访谈记录、调整建议、Avatar 版本和相关文件，删除后无法恢复。')}</p>
        </div>
      ),
      okText: t('确认永久删除'),
      cancelText: t('取消'),
      okButtonProps: { danger: true, loading: working },
      onOk: () => permanentlyDeleteCase(item),
    })
  }

  function logout() {
    staffTokenStore.clear()
    navigate('/admin/login', { replace: true })
  }

  if (loading) return <div className="route-fallback"><Spin size="large" tip={t('正在加载受限管理后台…')} /></div>

  const overview = (
    <div className="admin-overview">
      <div className="admin-stat-grid">
        <Card><Statistic title={t('医护账号')} value={stats?.doctors.total ?? 0} prefix={<TeamOutlined />} suffix={<small>{stats?.doctors.pending ?? 0} {t('待审批')}</small>} /></Card>
        <Card><Statistic title={t('进行中病例')} value={stats?.cases.in_progress ?? 0} prefix={<DatabaseOutlined />} /></Card>
        <Card><Statistic title={t('已归档病例')} value={archivedCases.length} prefix={<DatabaseOutlined />} /></Card>
        <Card><Statistic title={t('累计风险拦截')} value={stats?.risk_blocks ?? 0} prefix={<SafetyCertificateOutlined />} /></Card>
        <Card><Statistic title={t('删除任务异常')} value={(stats?.retention_jobs.retrying ?? 0) + (stats?.retention_jobs.failed ?? 0)} prefix={<AuditOutlined />} /></Card>
      </div>
      {stats?.alerts.map((item) => {
        const alertMessage = t(operationalAlertLabels[item.code] ?? item.message)
        return (
          <Alert
            key={item.code}
            type={item.severity === 'critical' ? 'error' : item.severity}
            showIcon
            message={language === 'en' ? `${alertMessage} (${item.count} ${t('项')})` : `${alertMessage}（${item.count} ${t('项')}）`}
          />
        )
      })}
    </div>
  )

  const accountTable = (
    <>
      <div className="admin-table-toolbar">
        <Input
          allowClear
          value={accountSearch}
          onChange={(event) => setAccountSearch(event.target.value)}
          placeholder={t('搜索医生姓名或邮箱')}
          aria-label={t('搜索医生姓名或邮箱')}
        />
        <Select
          value={accountApproval}
          onChange={setAccountApproval}
          aria-label={t('筛选审批状态')}
          options={[
            { value: 'all', label: t('全部审批状态') },
            { value: 'pending', label: t('待审批') },
            { value: 'approved', label: t('已批准') },
            { value: 'rejected', label: t('已拒绝') },
          ]}
        />
        <Select
          value={accountStatus}
          onChange={setAccountStatus}
          aria-label={t('筛选账号状态')}
          options={[
            { value: 'all', label: t('全部账号状态') },
            { value: 'enabled', label: t('启用') },
            { value: 'disabled', label: t('停用') },
          ]}
        />
      </div>
      <Table
        rowKey="user_id"
        dataSource={filteredDoctors}
        locale={{ emptyText: t('暂无匹配的医生账户') }}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        columns={[
          { title: t('医生'), key: 'doctor', render: (_, item) => <div className="admin-doctor-cell"><strong>{t(item.display_name)}</strong><span>{item.email}</span></div> },
          { title: t('邮箱验证'), dataIndex: 'email_verified', render: (value) => value ? <Tag color="green">{t('已验证')}</Tag> : <Tag color="gold">{t('待验证')}</Tag> },
          { title: t('审批'), dataIndex: 'approval_status', render: (value: AdminDoctor['approval_status']) => <Tag color={approvalLabels[value].color}>{t(approvalLabels[value].text)}</Tag> },
          { title: t('状态'), dataIndex: 'is_active', render: (value) => value ? <Tag color="blue">{t('启用')}</Tag> : <Tag>{t('停用')}</Tag> },
          { title: t('申请时间'), dataIndex: 'created_at', render: (value) => new Date(value).toLocaleString(language) },
          { title: t('操作'), key: 'actions', render: (_, item) => <Space wrap>
            {item.approval_status === 'pending' && <><Button type="primary" size="small" loading={working} onClick={() => void updateDoctor(item, { approval_status: 'approved' })}>{t('批准')}</Button><Button danger size="small" loading={working} onClick={() => void updateDoctor(item, { approval_status: 'rejected' })}>{t('拒绝')}</Button></>}
            {item.approval_status === 'approved' && <Popconfirm title={item.is_active ? t('确认停用该医生？现有登录将立即失效。') : t('确认重新启用该医生？')} onConfirm={() => void updateDoctor(item, { is_active: !item.is_active })}><Button size="small" danger={item.is_active}>{item.is_active ? t('停用') : t('启用')}</Button></Popconfirm>}
          </Space> },
        ]}
      />
    </>
  )

  const ruleTable = (
    <>
      <div className="admin-table-toolbar">
        <Input
          allowClear
          value={ruleSearch}
          onChange={(event) => setRuleSearch(event.target.value)}
          placeholder={t('搜索规则编号或类别')}
          aria-label={t('搜索规则编号或类别')}
        />
        <Select
          value={ruleStatus}
          onChange={setRuleStatus}
          aria-label={t('筛选规则状态')}
          options={[
            { value: 'all', label: t('全部规则状态') },
            { value: 'enabled', label: t('启用') },
            { value: 'disabled', label: t('停用') },
          ]}
        />
      </div>
      <Table
        rowKey="rule_id"
        dataSource={filteredRules}
        locale={{ emptyText: t('暂无匹配的安全规则') }}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        columns={[
          { title: t('编号'), dataIndex: 'rule_code', width: 90 },
          { title: t('类别'), dataIndex: 'category' },
          { title: t('匹配方式'), dataIndex: 'rule_type', render: (value: AdminRiskRule['rule_type']) => <Tag>{t(ruleTypeLabels[value])}</Tag> },
          { title: t('触发词数'), dataIndex: 'trigger_terms', render: (value: string[]) => value.length },
          { title: t('版本'), dataIndex: 'version' },
          { title: t('状态'), dataIndex: 'is_enabled', render: (value) => value ? <Tag color="green">{t('启用')}</Tag> : <Tag>{t('停用')}</Tag> },
          { title: t('操作'), render: (_, item) => <Button icon={<SettingOutlined />} onClick={() => openRuleEditor(item)}>{t('维护规则')}</Button> },
        ]}
      />
    </>
  )

  const auditTable = (
    <>
      <div className="admin-table-toolbar">
        <Input
          allowClear
          value={auditSearch}
          onChange={(event) => setAuditSearch(event.target.value)}
          placeholder={t('搜索操作事件')}
          aria-label={t('搜索操作事件')}
        />
        <Select
          value={auditActor}
          onChange={setAuditActor}
          aria-label={t('筛选操作者')}
          options={[
            { value: 'all', label: t('全部操作者') },
            { value: 'admin', label: t('管理员') },
            { value: 'doctor', label: t('医生') },
            { value: 'patient', label: t('患者') },
            { value: 'system', label: t('系统') },
          ]}
        />
        <Select
          value={auditResult}
          onChange={setAuditResult}
          aria-label={t('筛选操作结果')}
          options={[
            { value: 'all', label: t('全部结果') },
            { value: 'success', label: t('成功') },
            { value: 'blocked', label: t('已拦截') },
            { value: 'failed', label: t('失败') },
          ]}
        />
      </div>
      <Table
        rowKey="audit_id"
        dataSource={filteredAudits}
        locale={{ emptyText: t('暂无匹配的审计记录') }}
        pagination={{ pageSize: 12, showSizeChanger: false }}
        columns={[
          { title: t('时间'), dataIndex: 'created_at', width: 180, render: (value) => new Date(value).toLocaleString(language) },
          { title: t('操作者'), dataIndex: 'actor_type', width: 120, render: (value: AdminAuditEvent['actor_type']) => <Tag>{t(actorLabels[value])}</Tag> },
          { title: t('事件'), dataIndex: 'action', render: (value: string) => t(auditActionLabels[value] ?? value) },
          { title: t('结果'), dataIndex: 'result', width: 110, render: (value: AdminAuditEvent['result']) => <Tag color={resultLabels[value].color}>{t(resultLabels[value].text)}</Tag> },
          { title: t('操作摘要'), dataIndex: 'metadata', render: (value: Record<string, unknown> | null) => <span className="admin-audit-summary">{describeAuditMetadata(value)}</span> },
        ]}
      />
    </>
  )

  const retentionPanel = (
    <div className="admin-retention-grid">
      <Card title={t('归档病例管理')}>
        <Alert
          className="admin-retention-warning"
          type="warning"
          showIcon
          message={t('归档病例默认在到期后自动删除；管理员也可以提前永久删除。')}
          description={t('立即删除不可撤销，只能用于已经归档且确认不再需要保留的病例。')}
        />
        <div className="admin-table-toolbar admin-table-toolbar--retention">
          <Input
            allowClear
            value={retentionSearch}
            onChange={(event) => setRetentionSearch(event.target.value)}
            placeholder={t('搜索预约号')}
            aria-label={t('搜索预约号')}
          />
          <span>{t('仅显示归档病例的预约号和保留时间，不显示患者会话内容。')}</span>
        </div>
        <Table
          rowKey="case_id"
          dataSource={filteredArchivedCases}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{ emptyText: t('暂无匹配的归档病例') }}
          columns={[
            { title: t('预约号'), dataIndex: 'study_code', render: (value) => <strong className="admin-appointment-id">{value}</strong> },
            { title: t('归档时间'), dataIndex: 'archived_at', render: (value) => new Date(value).toLocaleString(language) },
            { title: t('永久删除时间'), dataIndex: 'retention_due_at', render: (value) => new Date(value).toLocaleString(language) },
            { title: t('保留状态'), dataIndex: 'restorable', render: (value) => value ? <Tag color="green">{t('保留期内')}</Tag> : <Tag color="red">{t('已到期')}</Tag> },
            {
              title: t('操作'),
              render: (_, item) => (
                <Space wrap>
                  <Popconfirm title={t('恢复不会恢复旧患者会话，也不会延后删除时间。')} onConfirm={() => void restoreCase(item)}>
                    <Button disabled={!item.restorable} loading={working}>{t('恢复为草稿')}</Button>
                  </Popconfirm>
                  <Button
                    danger
                    icon={<DeleteOutlined />}
                    disabled={working}
                    onClick={() => confirmPermanentDelete(item)}
                  >
                    {t('立即删除')}
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )

  return (
    <div className="admin-page">
      {messageContext}
      <header className="admin-header">
        <div><Brand /><span>{t('独立管理后台')}</span></div>
        <div className="admin-header__actions">
          <LanguageSwitcher />
          <Button icon={<LogoutOutlined />} onClick={logout}>{t('退出管理')}</Button>
        </div>
      </header>
      <main className="admin-content">
        <div className="admin-title"><span className="eyebrow">{t('平台管理')}</span><h1>{t('安全、权限与运行状态')}</h1><p>{t('管理医护账号、安全规则、操作审计和数据保留，不接触患者会话内容。')}</p></div>
        {error && <Alert type="error" showIcon message={error} />}
        <Tabs
          defaultActiveKey="overview"
          items={[
            { key: 'overview', label: <span><SafetyCertificateOutlined /> {t('总览')}</span>, children: overview },
            { key: 'accounts', label: <span><TeamOutlined /> {t('医护账号')}</span>, children: <Card className="admin-table-card" title={t('医护账号管理')}>{accountTable}</Card> },
            { key: 'rules', label: <span><SettingOutlined /> {t('安全规则')}</span>, children: <Card className="admin-table-card" title={t('内容安全规则')}><Alert type="warning" showIcon message={t('规则修改必须更新版本号，只影响修改后的新请求。')} />{ruleTable}</Card> },
            { key: 'audit', label: <span><AuditOutlined /> {t('操作审计')}</span>, children: <Card className="admin-table-card" title={t('最近操作记录')}>{auditTable}</Card> },
            { key: 'retention', label: <span><DatabaseOutlined /> {t('数据保留')}</span>, children: retentionPanel },
          ]}
        />
      </main>

      <Modal title={`${editingRule?.rule_code ?? ''} ${t('风险规则维护')}`} open={Boolean(editingRule)} footer={null} onCancel={() => setEditingRule(null)} width={720}>
        <Alert type="info" showIcon message={t('审计只记录变更字段和新版本号，不记录完整风险词内容。')} />
        <Form form={ruleForm} layout="vertical" onFinish={(values) => void saveRule(values)} className="admin-rule-form">
          <Form.Item name="category" label={t('风险类别')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="trigger_terms" label={t('触发词（每行一个）')} rules={[{ required: true }]}><Input.TextArea autoSize={{ minRows: 4, maxRows: 8 }} /></Form.Item>
          {editingRule?.rule_type === 'context' && <Form.Item name="context_terms" label={t('关联条件（每行一个）')} rules={[{ required: true }]}><Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} /></Form.Item>}
          <Form.Item name="exclusion_terms" label={t('排除条件（直接命中规则不会使用）')}><Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
          <div className="admin-rule-form__row"><Form.Item name="version" label={t('新规则版本')} rules={[{ required: true }, { validator: (_, value) => value === editingRule?.version ? Promise.reject(new Error(t('版本号必须更新'))) : Promise.resolve() }]}><Input placeholder={t('例如 RISK-V1.1')} /></Form.Item><Form.Item name="is_enabled" label={t('启用状态')} valuePropName="checked"><Switch /></Form.Item></div>
          <Button type="primary" htmlType="submit" block size="large" loading={working} icon={<CheckCircleOutlined />}>{t('保存规则变更')}</Button>
        </Form>
      </Modal>
    </div>
  )
}
