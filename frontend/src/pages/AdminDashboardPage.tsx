import {
  AuditOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
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
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  ApiClientError,
  apiRequest,
  type AdminArchivedCase,
  type AdminArchivedCaseList,
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

const retentionLabels = {
  scheduled: { text: '等待到期', color: 'blue' },
  running: { text: '正在删除', color: 'processing' },
  retrying: { text: '等待重试', color: 'orange' },
  completed: { text: '已永久删除', color: 'green' },
  failed: { text: '需要处理', color: 'red' },
}

function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean))]
}

export function AdminDashboardPage() {
  const navigate = useNavigate()
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
      setError(requestError instanceof Error ? requestError.message : '管理后台暂时无法加载')
    } finally {
      setLoading(false)
    }
  }, [navigate])

  useEffect(() => void loadDashboard(), [loadDashboard])

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
      messageApi.success('医生账户权限已更新')
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '账户更新失败')
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
      messageApi.success('风险规则已更新，只影响新的患者请求')
      setEditingRule(null)
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '规则更新失败')
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
      messageApi.success('病例已恢复为草稿；原30天删除时间保持不变')
      await loadDashboard()
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '病例恢复失败')
    } finally {
      setWorking(false)
    }
  }

  function logout() {
    staffTokenStore.clear()
    navigate('/admin/login', { replace: true })
  }

  if (loading) return <div className="route-fallback"><Spin size="large" tip="正在加载受限管理后台…" /></div>

  const overview = (
    <div className="admin-overview">
      <Alert
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="管理权限与病例内容严格隔离"
        description="此处只提供账户、规则、聚合统计、脱敏审计和归档恢复。系统不会向管理员返回研究编号、Q1–Q8、患者调整原文、Prompt 或 Avatar 图片。"
      />
      <div className="admin-stat-grid">
        <Card><Statistic title="医生账户" value={stats?.doctors.total ?? 0} prefix={<TeamOutlined />} suffix={<small>{stats?.doctors.pending ?? 0} 待审批</small>} /></Card>
        <Card><Statistic title="进行中病例" value={stats?.cases.in_progress ?? 0} prefix={<DatabaseOutlined />} /></Card>
        <Card><Statistic title="风险拦截事件" value={stats?.risk_blocks ?? 0} prefix={<SafetyCertificateOutlined />} /></Card>
        <Card><Statistic title="删除任务异常" value={(stats?.retention_jobs.retrying ?? 0) + (stats?.retention_jobs.failed ?? 0)} prefix={<AuditOutlined />} /></Card>
        <Card><Statistic title="生图完成率" value={(stats?.generation_success_rate ?? 0) * 100} precision={1} suffix="%" prefix={<CheckCircleOutlined />} /></Card>
        <Card><Statistic title="平均生图耗时" value={stats?.average_generation_seconds ?? 0} precision={1} suffix="秒" prefix={<SettingOutlined />} /></Card>
      </div>
      {stats?.alerts.map((item) => (
        <Alert
          key={item.code}
          type={item.severity === 'critical' ? 'error' : item.severity}
          showIcon
          message={`${item.message}（${item.count} 项）`}
        />
      ))}
      <Card title="系统边界状态" className="admin-boundary-card">
        <div><span>生图供应商</span><Tag>尚未配置</Tag></div>
        <div><span>调整文本风险规则</span><Tag color="green">后端强制执行</Tag></div>
        <div><span>病例删除期限</span><Tag color="blue">归档起固定30天</Tag></div>
        <div><span>管理员病例内容权限</span><Tag color="red">禁止访问</Tag></div>
      </Card>
    </div>
  )

  const accountTable = (
    <Table
      rowKey="user_id"
      dataSource={doctors}
      pagination={false}
      columns={[
        { title: '医生', key: 'doctor', render: (_, item) => <div className="admin-doctor-cell"><strong>{item.display_name}</strong><span>{item.email}</span></div> },
        { title: '邮箱验证', dataIndex: 'email_verified', render: (value) => value ? <Tag color="green">已验证</Tag> : <Tag color="gold">待验证</Tag> },
        { title: '审批', dataIndex: 'approval_status', render: (value: AdminDoctor['approval_status']) => <Tag color={approvalLabels[value].color}>{approvalLabels[value].text}</Tag> },
        { title: '状态', dataIndex: 'is_active', render: (value) => value ? <Tag color="blue">启用</Tag> : <Tag>停用</Tag> },
        { title: '申请时间', dataIndex: 'created_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
        { title: '操作', key: 'actions', render: (_, item) => <Space wrap>
          {item.approval_status === 'pending' && <><Button type="primary" size="small" loading={working} onClick={() => void updateDoctor(item, { approval_status: 'approved' })}>批准</Button><Button danger size="small" loading={working} onClick={() => void updateDoctor(item, { approval_status: 'rejected' })}>拒绝</Button></>}
          {item.approval_status === 'approved' && <Popconfirm title={item.is_active ? '确认停用该医生？现有登录将立即失效。' : '确认重新启用该医生？'} onConfirm={() => void updateDoctor(item, { is_active: !item.is_active })}><Button size="small" danger={item.is_active}>{item.is_active ? '停用' : '启用'}</Button></Popconfirm>}
        </Space> },
      ]}
    />
  )

  const ruleTable = (
    <Table
      rowKey="rule_id"
      dataSource={rules}
      pagination={false}
      columns={[
        { title: '编号', dataIndex: 'rule_code', width: 90 },
        { title: '类别', dataIndex: 'category' },
        { title: '匹配方式', dataIndex: 'rule_type', render: (value) => <Tag>{value}</Tag> },
        { title: '触发词数', dataIndex: 'trigger_terms', render: (value: string[]) => value.length },
        { title: '版本', dataIndex: 'version' },
        { title: '状态', dataIndex: 'is_enabled', render: (value) => value ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
        { title: '操作', render: (_, item) => <Button icon={<SettingOutlined />} onClick={() => openRuleEditor(item)}>维护规则</Button> },
      ]}
    />
  )

  const auditTable = (
    <Table
      rowKey="audit_id"
      dataSource={audits?.items ?? []}
      pagination={{ pageSize: 12 }}
      columns={[
        { title: '时间', dataIndex: 'created_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
        { title: '操作者', dataIndex: 'actor_type', render: (value) => <Tag>{value}</Tag> },
        { title: '事件', dataIndex: 'action' },
        { title: '结果', dataIndex: 'result', render: (value) => <Tag color={value === 'success' ? 'green' : value === 'blocked' ? 'orange' : 'red'}>{value}</Tag> },
        { title: '脱敏元数据', dataIndex: 'metadata', render: (value) => value ? <code>{JSON.stringify(value)}</code> : '—' },
      ]}
    />
  )

  const retentionPanel = (
    <div className="admin-retention-grid">
      <Card title="可恢复的归档病例" extra={<span>不显示研究编号及病例内容</span>}>
        <Table
          rowKey="case_id"
          dataSource={archivedCases}
          pagination={false}
          locale={{ emptyText: '暂无归档病例' }}
          columns={[
            { title: '脱敏引用', dataIndex: 'case_id', render: (value: string) => <code>{value.slice(0, 8)}…</code> },
            { title: '归档时间', dataIndex: 'archived_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
            { title: '永久删除时间', dataIndex: 'retention_due_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
            { title: '操作', render: (_, item) => <Popconfirm title="恢复不会恢复旧患者会话，也不会延后删除时间。" onConfirm={() => void restoreCase(item)}><Button disabled={!item.restorable} loading={working}>恢复为草稿</Button></Popconfirm> },
          ]}
        />
      </Card>
      <Card title="永久删除任务">
        <Table
          rowKey="retention_job_id"
          dataSource={retentionJobs}
          pagination={false}
          columns={[
            { title: '到期时间', dataIndex: 'retention_due_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
            { title: '状态', dataIndex: 'status', render: (value: keyof typeof retentionLabels) => <Tag color={retentionLabels[value].color}>{retentionLabels[value].text}</Tag> },
            { title: '尝试次数', dataIndex: 'attempt_count' },
            { title: '脱敏错误', dataIndex: 'last_error_code', render: (value) => value ?? '—' },
          ]}
        />
      </Card>
    </div>
  )

  return (
    <div className="admin-page">
      {messageContext}
      <header className="admin-header">
        <div><Brand /><span>独立管理后台</span></div>
        <Button icon={<LogoutOutlined />} onClick={logout}>退出管理</Button>
      </header>
      <main className="admin-content">
        <div className="admin-title"><span className="eyebrow">系统治理</span><h1>安全、权限与数据生命周期</h1><p>仅展示管理操作所需的最少信息</p></div>
        {error && <Alert type="error" showIcon message={error} />}
        <Tabs
          defaultActiveKey="overview"
          items={[
            { key: 'overview', label: <span><SafetyCertificateOutlined /> 总览</span>, children: overview },
            { key: 'accounts', label: <span><TeamOutlined /> 医生账户</span>, children: <Card className="admin-table-card" title="账户审批与启停">{accountTable}</Card> },
            { key: 'rules', label: <span><SettingOutlined /> 风险规则</span>, children: <Card className="admin-table-card" title="后端风险规则"><Alert type="warning" showIcon message="规则修改必须更新版本号，只影响修改后的新请求。" />{ruleTable}</Card> },
            { key: 'audit', label: <span><AuditOutlined /> 脱敏审计</span>, children: <Card className="admin-table-card" title="最近审计事件">{auditTable}</Card> },
            { key: 'retention', label: <span><DatabaseOutlined /> 归档与删除</span>, children: retentionPanel },
          ]}
        />
      </main>

      <Modal title={`${editingRule?.rule_code ?? ''} 风险规则维护`} open={Boolean(editingRule)} footer={null} onCancel={() => setEditingRule(null)} width={720}>
        <Alert type="info" showIcon message="审计只记录变更字段和新版本号，不记录完整风险词内容。" />
        <Form form={ruleForm} layout="vertical" onFinish={(values) => void saveRule(values)} className="admin-rule-form">
          <Form.Item name="category" label="风险类别" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="trigger_terms" label="触发词（每行一个）" rules={[{ required: true }]}><Input.TextArea autoSize={{ minRows: 4, maxRows: 8 }} /></Form.Item>
          {editingRule?.rule_type === 'context' && <Form.Item name="context_terms" label="关联条件（每行一个）" rules={[{ required: true }]}><Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} /></Form.Item>}
          <Form.Item name="exclusion_terms" label="排除条件（直接命中规则不会使用）"><Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
          <div className="admin-rule-form__row"><Form.Item name="version" label="新规则版本" rules={[{ required: true }, { validator: (_, value) => value === editingRule?.version ? Promise.reject(new Error('版本号必须更新')) : Promise.resolve() }]}><Input placeholder="例如 RISK-V1.1" /></Form.Item><Form.Item name="is_enabled" label="启用状态" valuePropName="checked"><Switch /></Form.Item></div>
          <Button type="primary" htmlType="submit" block size="large" loading={working} icon={<CheckCircleOutlined />}>保存规则变更</Button>
        </Form>
      </Modal>
    </div>
  )
}
