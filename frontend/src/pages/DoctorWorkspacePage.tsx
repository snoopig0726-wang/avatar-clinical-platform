import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  ClockCircleOutlined,
  FileAddOutlined,
  FolderOpenOutlined,
  LogoutOutlined,
  MoreOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Dropdown,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
  type TableColumnsType,
} from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  ApiClientError,
  apiRequest,
  type CaseListResponse,
  type ClinicalCase,
  newIdempotencyKey,
  type SessionInvite,
  staffTokenStore,
  type StaffUser,
} from '../lib/api'

const { Header, Sider, Content } = Layout

const statusMeta: Record<ClinicalCase['status'], { label: string; color: string; stage: string }> = {
  draft: { label: '草稿', color: 'default', stage: '等待创建邀请码或录入访谈' },
  in_progress: { label: '进行中', color: 'processing', stage: '受监督访谈与特征确认' },
  completed: { label: '已完成', color: 'success', stage: '等待归档' },
  archived: { label: '已归档', color: 'default', stage: '30 天留存倒计时' },
}

function relativeTime(value: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`
  return new Date(value).toLocaleDateString('zh-CN')
}

export function DoctorWorkspacePage() {
  const navigate = useNavigate()
  const [messageApi, messageContext] = message.useMessage()
  const [activeSection, setActiveSection] = useState('overview')
  const overviewRef = useRef<HTMLDivElement>(null)
  const casesRef = useRef<HTMLElement>(null)
  const safetyRef = useRef<HTMLDivElement>(null)
  const [user, setUser] = useState<StaffUser | null>(null)
  const [cases, setCases] = useState<ClinicalCase[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [invite, setInvite] = useState<SessionInvite | null>(null)
  const [form] = Form.useForm<{ study_code: string }>()

  const loadWorkspace = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [currentUser, caseList] = await Promise.all([
        apiRequest<StaffUser>('/users/me', { staffToken: token }),
        apiRequest<CaseListResponse>('/cases?page=1&page_size=100', { staffToken: token }),
      ])
      setUser(currentUser)
      setCases(caseList.items)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
        return
      }
      setError(requestError instanceof Error ? requestError.message : '工作台加载失败')
    } finally {
      setLoading(false)
    }
  }, [navigate])

  useEffect(() => void loadWorkspace(), [loadWorkspace])

  async function createCase(values: { study_code: string }) {
    const token = staffTokenStore.get()
    if (!token) return
    setCreating(true)
    try {
      const created = await apiRequest<ClinicalCase>('/cases', {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('case-create'),
        body: { study_code: values.study_code.trim().toUpperCase() },
      })
      setCases((current) => [created, ...current])
      setCreateOpen(false)
      form.resetFields()
      messageApi.success('匿名病例已创建')
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '创建失败')
    } finally {
      setCreating(false)
    }
  }

  async function createInvite(record: ClinicalCase) {
    const token = staffTokenStore.get()
    if (!token) return
    try {
      const created = await apiRequest<SessionInvite>(
        `/cases/${record.case_id}/session-invites`,
        {
          method: 'POST',
          staffToken: token,
          idempotencyKey: newIdempotencyKey('invite-create'),
          body: { expires_in_hours: 24 },
        },
      )
      setInvite(created)
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '邀请码创建失败')
    }
  }

  async function logout() {
    const token = staffTokenStore.get()
    if (token) {
      await apiRequest('/auth/logout', { method: 'POST', staffToken: token }).catch(() => undefined)
    }
    staffTokenStore.clear()
    navigate('/doctor/login', { replace: true })
  }

  const columns = useMemo<TableColumnsType<ClinicalCase>>(
    () => [
      {
        title: '匿名病例',
        dataIndex: 'study_code',
        render: (value: string, record) => (
          <button
            type="button"
            className="case-id-cell case-id-cell--button"
            onClick={() => navigate(`/doctor/cases/${record.case_id}`)}
          >
            <span className="case-id-cell__icon">
              <FolderOpenOutlined />
            </span>
            <span>
              <strong>{value}</strong>
              <small>去标识化研究编号</small>
            </span>
          </button>
        ),
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 120,
        render: (value: ClinicalCase['status']) => (
          <Tag color={statusMeta[value].color}>{statusMeta[value].label}</Tag>
        ),
      },
      {
        title: '当前阶段',
        dataIndex: 'status',
        responsive: ['md'],
        render: (value: ClinicalCase['status'], record) => (
          <div className="stage-cell">
            <strong>{statusMeta[value].stage}</strong>
            <small>
              {record.active_session_count > 0
                ? `${record.active_session_count} 个受监督会话`
                : '当前无活动会话'}
            </small>
          </div>
        ),
      },
      {
        title: '最近更新',
        dataIndex: 'updated_at',
        width: 130,
        responsive: ['md'],
        render: (value: string) => <span className="muted-cell">{relativeTime(value)}</span>,
      },
      {
        title: '',
        key: 'actions',
        width: 64,
        align: 'right',
        render: (_, record) => (
          <Dropdown
            menu={{
              items: [
                {
                  key: 'open',
                  label: '打开病例',
                  onClick: () => navigate(`/doctor/cases/${record.case_id}`),
                },
                {
                  key: 'invite',
                  label: '创建邀请码',
                  disabled: record.status === 'archived',
                  onClick: () => void createInvite(record),
                },
              ],
            }}
          >
            <Button type="text" icon={<MoreOutlined />} aria-label="更多病例操作" />
          </Dropdown>
        ),
      },
    ],
    [navigate],
  )

  const activeCases = cases.filter((item) => item.status === 'in_progress').length
  const activeSessions = cases.reduce((sum, item) => sum + item.active_session_count, 0)
  const today = new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date())

  function navigateSection(key: string) {
    setActiveSection(key)
    const target =
      key === 'cases'
        ? casesRef.current
        : key === 'safety'
          ? safetyRef.current
          : overviewRef.current
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <Layout className="workspace-layout">
      {messageContext}
      <Sider width={248} className="workspace-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="workspace-brand">
          <Brand inverse />
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeSection]}
          onClick={({ key }) => navigateSection(key)}
          items={[
            { key: 'overview', icon: <AppstoreOutlined />, label: '工作台概览' },
            { key: 'cases', icon: <FolderOpenOutlined />, label: '病例管理' },
            { key: 'safety', icon: <SafetyCertificateOutlined />, label: '安全与授权' },
          ]}
        />
        <div className="workspace-sider__bottom">
          <Menu
            theme="dark"
            mode="inline"
            selectable={false}
            items={[
              { key: 'logout', icon: <LogoutOutlined />, label: '安全退出', onClick: logout },
            ]}
          />
          <div className="workspace-sider__boundary">
            <SafetyCertificateOutlined />
            <span>临床研究内部系统</span>
          </div>
        </div>
      </Sider>

      <Layout>
        <Header className="workspace-header">
          <div>
            <span className="workspace-header__context">医生工作台</span>
            <strong>受监督 Avatar 研究平台</strong>
          </div>
          <div className="workspace-header__actions">
            <Tooltip title="暂无新通知">
              <Badge dot>
                <Button type="text" shape="circle" icon={<BellOutlined />} />
              </Badge>
            </Tooltip>
            <div className="doctor-profile">
              <Avatar icon={<UserOutlined />} />
              <span>
                <strong>{user?.display_name ?? '医生'}</strong>
                <small>已审批 · 当前在线</small>
              </span>
            </div>
          </div>
        </Header>

        <Content className="workspace-content">
          <div className="workspace-welcome" ref={overviewRef}>
            <div>
              <span className="eyebrow">{today}</span>
              <h1>你好，{user?.display_name ?? '医生'}</h1>
              <p>这里仅显示由当前账户创建和负责的去标识化病例。</p>
            </div>
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              创建匿名病例
            </Button>
          </div>

          {error && <Alert type="error" showIcon message="工作台暂时不可用" description={error} />}

          <section className="stat-grid" aria-label="工作台统计">
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--green"><FolderOpenOutlined /></span>
              <div><small>进行中病例</small><strong>{activeCases}</strong><span>仅显示你创建的病例</span></div>
            </Card>
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--amber"><AuditOutlined /></span>
              <div><small>版本审核入口</small><strong>{cases.length}</strong><span>在对应病例中完成审核与授权</span></div>
            </Card>
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--blue"><ClockCircleOutlined /></span>
              <div><small>当前受监督会话</small><strong>{activeSessions}</strong><span>含等待、进行中和暂停会话</span></div>
            </Card>
          </section>

          <section className="workspace-main-grid" ref={casesRef}>
            <Card className="cases-card" title="最近病例" extra={<Button type="link">共 {cases.length} 个</Button>}>
              <Table
                columns={columns}
                dataSource={cases}
                pagination={false}
                rowKey="case_id"
                loading={loading}
                locale={{ emptyText: '尚未创建匿名病例' }}
              />
            </Card>
            <div className="workspace-side-column" ref={safetyRef}>
              <Card className="review-card" title="开发进度">
                <div className="review-item">
                  <span className="review-item__icon"><UserOutlined /></span>
                  <div><strong>病例与会话闭环已启用</strong><p>真实数据库、权限及一次性邀请码</p><Button type="link" onClick={() => setCreateOpen(true)}>创建首个病例</Button></div>
                </div>
              </Card>
              <Card className="safety-card">
                <div className="safety-card__heading"><SafetyCertificateOutlined /><div><strong>当前安全门禁</strong><span>业务权限和会话隔离已启用</span></div></div>
                <Space direction="vertical" size={14} style={{ width: '100%' }}>
                  <div className="safety-progress"><span>接口权限覆盖</span><strong>100%</strong></div>
                  <Progress percent={100} showInfo={false} size="small" strokeColor="#3f7f63" />
                  <div className="safety-progress"><span>GPT Image 2 适配器</span><strong>已接入 · 当前 Mock</strong></div>
                  <Progress percent={100} showInfo={false} size="small" strokeColor="#6f8f84" />
                </Space>
              </Card>
            </div>
          </section>
          <Button className="floating-create" type="primary" shape="circle" icon={<FileAddOutlined />} onClick={() => setCreateOpen(true)} />
        </Content>
      </Layout>

      <Modal title="创建匿名病例" open={createOpen} onCancel={() => setCreateOpen(false)} footer={null}>
        <Alert type="info" showIcon message="只填写去标识化研究编号，不得录入姓名、联系方式或医院病历号。" />
        <Form form={form} layout="vertical" onFinish={createCase} className="modal-form">
          <Form.Item label="研究编号" name="study_code" rules={[{ required: true, message: '请输入研究编号' }, { pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{2,99}$/, message: '仅支持字母、数字、下划线和连字符' }]}>
            <Input placeholder="例如 ST-2026-0001" autoFocus />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={creating}>创建病例</Button>
        </Form>
      </Modal>

      <Modal title="一次性患者邀请码" open={Boolean(invite)} onCancel={() => setInvite(null)} footer={<Button type="primary" onClick={() => setInvite(null)}>完成</Button>}>
        <Alert type="success" showIcon message="邀请码已创建" description="请仅在现场监督会话中向患者提供。有效期 24 小时且只能兑换一次。" />
        <div className="invite-code-display">{invite?.code}</div>
        <Button block onClick={() => invite?.code && navigator.clipboard.writeText(invite.code)}>复制邀请码</Button>
      </Modal>
    </Layout>
  )
}
