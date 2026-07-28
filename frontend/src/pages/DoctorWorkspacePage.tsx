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
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  type CaseSafetyEvent,
  type CaseSafetyEventListResponse,
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
  archived: { label: '已归档', color: 'default', stage: '30 天过期' },
}

function relativeTime(value: string, locale: string, t: (source: string) => string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 1) return t('刚刚')
  if (minutes < 60) return locale === 'en' ? `${minutes} min ago` : `${minutes} ${t('分钟前')}`
  if (minutes < 1440) return locale === 'en' ? `${Math.floor(minutes / 60)} hr ago` : `${Math.floor(minutes / 60)} ${t('小时前')}`
  return new Date(value).toLocaleDateString(locale)
}

export function DoctorWorkspacePage() {
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const [messageApi, messageContext] = message.useMessage()
  const [activeSection, setActiveSection] = useState('overview')
  const overviewRef = useRef<HTMLDivElement>(null)
  const casesRef = useRef<HTMLElement>(null)
  const safetyRef = useRef<HTMLDivElement>(null)
  const [user, setUser] = useState<StaffUser | null>(null)
  const [cases, setCases] = useState<ClinicalCase[]>([])
  const [caseRows, setCaseRows] = useState<ClinicalCase[]>([])
  const [safetyEvents, setSafetyEvents] = useState<CaseSafetyEvent[]>([])
  const [caseTotal, setCaseTotal] = useState(0)
  const [casePage, setCasePage] = useState(1)
  const [casePageSize, setCasePageSize] = useState(5)
  const [caseQuery, setCaseQuery] = useState('')
  const [appliedCaseQuery, setAppliedCaseQuery] = useState('')
  const [caseTableLoading, setCaseTableLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [invite, setInvite] = useState<SessionInvite | null>(null)
  const [form] = Form.useForm<{ study_code: string }>()
  const knownSafetyEventIds = useRef<Set<number> | null>(null)
  const workspaceRefreshRunning = useRef(false)

  const loadCasePage = useCallback(async (page: number, pageSize: number, query: string) => {
    const token = staffTokenStore.get()
    if (!token) return
    setCaseTableLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      })
      if (query.trim()) params.set('q', query.trim())
      const result = await apiRequest<CaseListResponse>(`/cases?${params.toString()}`, {
        staffToken: token,
      })
      setCaseRows(result.items)
      setCaseTotal(result.total)
      setCasePage(result.page)
      setCasePageSize(result.page_size)
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('病例查询失败'))
    } finally {
      setCaseTableLoading(false)
    }
  }, [messageApi, t])

  const loadWorkspace = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [currentUser, caseList, firstPage, safetyResult] = await Promise.all([
        apiRequest<StaffUser>('/users/me', { staffToken: token }),
        apiRequest<CaseListResponse>('/cases?page=1&page_size=100', { staffToken: token }),
        apiRequest<CaseListResponse>('/cases?page=1&page_size=5', { staffToken: token }),
        apiRequest<CaseSafetyEventListResponse>('/cases/safety-events/recent', {
          staffToken: token,
        }),
      ])
      setUser(currentUser)
      setCases(caseList.items)
      setCaseRows(firstPage.items)
      setCaseTotal(firstPage.total)
      setCasePage(firstPage.page)
      setCasePageSize(firstPage.page_size)
      setSafetyEvents(safetyResult.items)
      knownSafetyEventIds.current = new Set(
        safetyResult.items.map((item) => item.event_id),
      )
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
        return
      }
      setError(requestError instanceof Error ? requestError.message : t('工作台加载失败'))
    } finally {
      setLoading(false)
    }
  }, [navigate, t])

  useEffect(() => void loadWorkspace(), [loadWorkspace])

  const loadWorkspaceRealtime = useCallback(async () => {
    const token = staffTokenStore.get()
    if (
      !token
      || document.visibilityState !== 'visible'
      || workspaceRefreshRunning.current
    ) return
    workspaceRefreshRunning.current = true
    try {
      const params = new URLSearchParams({
        page: String(casePage),
        page_size: String(casePageSize),
      })
      if (appliedCaseQuery) params.set('q', appliedCaseQuery)
      const [caseList, visiblePage, safetyResult] = await Promise.all([
        apiRequest<CaseListResponse>('/cases?page=1&page_size=100', {
          staffToken: token,
        }),
        apiRequest<CaseListResponse>(`/cases?${params.toString()}`, {
          staffToken: token,
        }),
        apiRequest<CaseSafetyEventListResponse>('/cases/safety-events/recent', {
          staffToken: token,
        }),
      ])

      const knownIds = knownSafetyEventIds.current
      const newEvents = knownIds
        ? safetyResult.items.filter((item) => !knownIds.has(item.event_id))
        : []
      if (newEvents.length > 0) {
        const latest = newEvents[0]
        Modal.warning({
          title: t('患者安全提醒'),
          content: `${latest.study_code} · ${t(
            latest.event_type === 'patient_discomfort'
              ? '患者表示不适，会话已安全暂停，请立即关注。'
              : '系统拦截了一条包含敏感内容的患者调整建议，请及时关注。',
          )}`,
          okText: t('查看病例'),
          onOk: () => navigate(`/doctor/cases/${latest.case_id}`),
        })
      }
      knownSafetyEventIds.current = new Set(
        safetyResult.items.map((item) => item.event_id),
      )
      setCases(caseList.items)
      setCaseRows(visiblePage.items)
      setCaseTotal(visiblePage.total)
      setSafetyEvents(safetyResult.items)
      setError(null)
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
      }
    } finally {
      workspaceRefreshRunning.current = false
    }
  }, [appliedCaseQuery, casePage, casePageSize, navigate, t])

  useEffect(() => {
    const refreshVisibleWorkspace = () => void loadWorkspaceRealtime()
    const timer = window.setInterval(refreshVisibleWorkspace, 2000)
    window.addEventListener('focus', refreshVisibleWorkspace)
    document.addEventListener('visibilitychange', refreshVisibleWorkspace)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refreshVisibleWorkspace)
      document.removeEventListener('visibilitychange', refreshVisibleWorkspace)
    }
  }, [loadWorkspaceRealtime])

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
      setCaseQuery('')
      setAppliedCaseQuery('')
      await loadCasePage(1, casePageSize, '')
      setCreateOpen(false)
      form.resetFields()
      messageApi.success(t('匿名病例已创建'))
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('创建失败'))
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
      messageApi.error(requestError instanceof Error ? requestError.message : t('邀请码创建失败'))
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
        title: t('预约号'),
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
            </span>
          </button>
        ),
      },
      {
        title: t('状态'),
        dataIndex: 'status',
        width: 120,
        align: 'center',
        render: (value: ClinicalCase['status']) => (
          <Tag color={statusMeta[value].color}>{t(statusMeta[value].label)}</Tag>
        ),
      },
      {
        title: t('当前阶段'),
        dataIndex: 'status',
        width: 190,
        align: 'center',
        responsive: ['md'],
        render: (value: ClinicalCase['status'], record) => (
          <div className="stage-cell">
            <strong>{t(statusMeta[value].stage)}</strong>
            <small>
              {record.active_session_count > 0
                ? language === 'en'
                  ? `${record.active_session_count}${t('个受监督会话')}`
                  : `${record.active_session_count} ${t('个受监督会话')}`
                : t('当前无活动会话')}
            </small>
          </div>
        ),
      },
      {
        title: t('最近更新'),
        dataIndex: 'updated_at',
        width: 148,
        align: 'center',
        responsive: ['md'],
        render: (value: string) => <span className="muted-cell">{relativeTime(value, language, t)}</span>,
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
                  label: t('打开病例'),
                  onClick: () => navigate(`/doctor/cases/${record.case_id}`),
                },
                {
                  key: 'invite',
                  label: t('创建邀请码'),
                  disabled: record.status === 'archived',
                  onClick: () => void createInvite(record),
                },
              ],
            }}
          >
            <Button type="text" icon={<MoreOutlined />} aria-label={t('更多病例操作')} />
          </Dropdown>
        ),
      },
    ],
    [language, navigate, t],
  )

  const activeCases = cases.filter((item) => item.status === 'in_progress').length
  const activeSessions = cases.reduce((sum, item) => sum + item.active_session_count, 0)
  const today = new Intl.DateTimeFormat(language, {
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
      <Sider width={288} className="workspace-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="workspace-brand">
          <Brand compact inverse />
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activeSection]}
          onClick={({ key }) => navigateSection(key)}
          items={[
            { key: 'overview', icon: <AppstoreOutlined />, label: t('工作台概览') },
            { key: 'cases', icon: <FolderOpenOutlined />, label: t('病例管理') },
            { key: 'safety', icon: <SafetyCertificateOutlined />, label: t('安全与授权') },
          ]}
        />
        <div className="workspace-sider__bottom">
          <Menu
            theme="dark"
            mode="inline"
            selectable={false}
            items={[
              { key: 'logout', icon: <LogoutOutlined />, label: t('安全退出'), onClick: logout },
            ]}
          />
          <div className="workspace-sider__boundary">
            <SafetyCertificateOutlined />
            <span>{t('医护专业工作空间')}</span>
          </div>
        </div>
      </Sider>

      <Layout>
        <Header className="workspace-header">
          <div>
            <span className="workspace-header__context">{t('医生工作台')}</span>
            <strong>{t('Avatar 治疗支持平台')}</strong>
          </div>
          <div className="workspace-header__actions">
            <LanguageSwitcher />
            <Tooltip title={safetyEvents.length ? t('查看近期患者安全提醒') : t('暂无新通知')}>
              <Badge count={safetyEvents.length} size="small" overflowCount={9}>
                <Button
                  type="text"
                  shape="circle"
                  icon={<BellOutlined />}
                  onClick={() => {
                    const latest = safetyEvents[0]
                    if (latest) navigate(`/doctor/cases/${latest.case_id}`)
                  }}
                />
              </Badge>
            </Tooltip>
            <div className="doctor-profile">
              <Avatar icon={<UserOutlined />} />
              <span>
                <strong>{t(user?.display_name ?? '医生')}</strong>
                <small>{t('已审批 · 当前在线')}</small>
              </span>
            </div>
          </div>
        </Header>

        <Content className="workspace-content">
          <div className="workspace-welcome" ref={overviewRef}>
            <div>
              <span className="eyebrow">{today}</span>
              <h1>{t('你好，')}{t(user?.display_name ?? '医生')}</h1>
              <p>{t('优先处理待审核图像和进行中会话；这里只显示由您负责的病例。')}</p>
            </div>
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              {t('创建匿名病例')}
            </Button>
          </div>

          {error && <Alert type="error" showIcon message={t('工作台暂时不可用')} description={error} />}
          {safetyEvents[0] && (
            <Alert
              className="workspace-safety-alert"
              type={safetyEvents[0].severity === 'critical' ? 'error' : 'warning'}
              showIcon
              message={`${safetyEvents[0].study_code} · ${t(
                safetyEvents[0].event_type === 'patient_discomfort'
                  ? '患者表示不适，请立即关注'
                  : '系统拦截了患者提交的敏感调整建议',
              )}`}
              description={`${new Date(safetyEvents[0].created_at).toLocaleString(language === 'en' ? 'en-US' : language)} · ${t('点击右侧按钮进入病例处理。')}`}
              action={(
                <Button
                  size="small"
                  danger={safetyEvents[0].severity === 'critical'}
                  onClick={() => navigate(`/doctor/cases/${safetyEvents[0].case_id}`)}
                >
                  {t('查看病例')}
                </Button>
              )}
            />
          )}

          <section className="stat-grid" aria-label={t('工作台统计')}>
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--green"><FolderOpenOutlined /></span>
              <div><small>{t('进行中病例')}</small><strong>{activeCases}</strong><span>{t('仅显示你创建的病例')}</span></div>
            </Card>
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--amber"><AuditOutlined /></span>
              <div><small>{t('版本审核入口')}</small><strong>{cases.length}</strong><span>{t('在对应病例中完成审核与授权')}</span></div>
            </Card>
            <Card className="stat-card">
              <span className="stat-card__icon stat-card__icon--blue"><ClockCircleOutlined /></span>
              <div><small>{t('当前受监督会话')}</small><strong>{activeSessions}</strong><span>{t('含等待、进行中和暂停会话')}</span></div>
            </Card>
          </section>

          <section className="workspace-main-grid" ref={casesRef}>
            <Card
              className="cases-card"
              title={t('最近病例')}
              extra={(
                <div className="cases-card__tools">
                  <Input.Search
                    allowClear
                    value={caseQuery}
                    placeholder={t('搜索预约号')}
                    aria-label={t('搜索预约号')}
                    onChange={(event) => {
                      setCaseQuery(event.target.value)
                      if (!event.target.value) {
                        setAppliedCaseQuery('')
                        void loadCasePage(1, casePageSize, '')
                      }
                    }}
                    onSearch={(value) => {
                      setAppliedCaseQuery(value.trim())
                      void loadCasePage(1, casePageSize, value)
                    }}
                  />
                  <Button type="link">{t('共')} {caseTotal} {t('个')}</Button>
                </div>
              )}
            >
              <Table
                columns={columns}
                dataSource={caseRows}
                pagination={{
                  current: casePage,
                  pageSize: casePageSize,
                  total: caseTotal,
                  showSizeChanger: true,
                  pageSizeOptions: [5, 10, 20],
                  showTotal: (total) => `${t('共')} ${total} ${t('个')}`,
                }}
                onChange={(pagination) => {
                  void loadCasePage(
                    pagination.current ?? 1,
                    pagination.pageSize ?? casePageSize,
                    appliedCaseQuery,
                  )
                }}
                rowKey="case_id"
                loading={loading || caseTableLoading}
                locale={{ emptyText: t('尚未创建匿名病例') }}
              />
            </Card>
            <div className="workspace-side-column" ref={safetyRef}>
              <Card className="review-card" title={t('今日工作提醒')}>
                <div className="review-item">
                  <span className="review-item__icon"><UserOutlined /></span>
                  <div><strong>{t('患者会话已准备就绪')}</strong><p>{t('创建病例后即可生成一次性邀请码，并在患者进入后开始访谈。')}</p><Button type="link" onClick={() => setCreateOpen(true)}>{t('创建新病例')}</Button></div>
                </div>
              </Card>
              <Card className="safety-card">
                <div className="safety-card__heading"><SafetyCertificateOutlined /><div><strong>{t('患者安全与授权')}</strong><span>{t('关键保护会自动执行')}</span></div></div>
                <Space direction="vertical" size={14} style={{ width: '100%' }}>
                  <div className="safety-progress"><span>{t('患者展示内容')}</span><strong>{t('仅限医生已审核版本')}</strong></div>
                  <Progress percent={100} showInfo={false} size="small" strokeColor="#3f7f63" />
                  <div className="safety-progress"><span>{t('患者安全暂停')}</span><strong>{t('随时可用 · 医生恢复')}</strong></div>
                  <Progress percent={100} showInfo={false} size="small" strokeColor="#6f8f84" />
                </Space>
              </Card>
            </div>
          </section>
          <Button className="floating-create" type="primary" shape="circle" icon={<FileAddOutlined />} aria-label={t('创建匿名病例')} onClick={() => setCreateOpen(true)} />
        </Content>
      </Layout>

      <Modal title={t('创建匿名病例')} open={createOpen} onCancel={() => setCreateOpen(false)} footer={null}>
        <Alert type="info" showIcon message={t('填写固定预约号，不得填写姓名、联系方式')} />
        <Form form={form} layout="vertical" onFinish={createCase} className="modal-form">
          <Form.Item label={t('预约号')} name="study_code" rules={[{ required: true, message: t('请输入预约号') }, { pattern: /^[A-Za-z0-9][A-Za-z0-9_-]{2,99}$/, message: t('仅支持字母、数字、下划线和连字符') }]}>
            <Input placeholder={t('例如 APPT-2026-0001')} autoFocus />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={creating}>{t('创建病例')}</Button>
        </Form>
      </Modal>

      <Modal title={t('一次性患者邀请码')} open={Boolean(invite)} onCancel={() => setInvite(null)} footer={<Button type="primary" onClick={() => setInvite(null)}>{t('完成')}</Button>}>
        <Alert type="success" showIcon message={t('邀请码已创建')} description={t('请仅在现场监督会话中向患者提供。有效期 24 小时且只能兑换一次。')} />
        <div className="invite-code-display">{invite?.code}</div>
        <Button block onClick={() => invite?.code && navigator.clipboard.writeText(invite.code)}>{t('复制邀请码')}</Button>
      </Modal>
    </Layout>
  )
}
