import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckCircleFilled,
  ExperimentOutlined,
  PictureOutlined,
  SaveOutlined,
  SafetyCertificateOutlined,
  SoundOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Modal,
  Progress,
  Radio,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Steps,
  Tag,
  message,
} from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  type AvatarVersion,
  type AvatarVersionList,
  type CaseSafetyEventListResponse,
  newIdempotencyKey,
  type PatientSession,
  staffTokenStore,
  type VisualFeatures,
  type VoiceFeatureContract,
  type VoiceFeatures,
} from '../lib/api'

const labels: Record<string, string> = {
  voice_gender: 'Q1 · 声音性别感',
  age_sense: 'Q2 · 声音年龄感',
  pitch_level: 'Q3 · 音调高低',
  speaking_rate_level: 'Q4 · 语速快慢',
  timbre: 'Q5 · 音色与口音',
  emotions: 'Q6 · 情绪线索（最多六项）',
  power_level: 'Q7 · 声音强大感',
  malice_level: 'Q8 · 声音恶意感',
}

const enumLabels: Record<string, string> = {
  male: '男性', female: '女性', uncertain_mixed: '不确定或混合',
  child: '儿童', adolescent: '青少年', young: '青年', middle_aged: '中年', elderly: '老年', uncertain: '不确定',
  hoarse_rough: '沙哑粗糙', clear_transparent: '清亮通透', sharp_piercing: '尖锐刺耳', low_rich: '低沉浑厚', breathy_weak: '气声虚弱', nasal: '鼻音偏重', mumbled: '口齿含糊', heavy_accent: '厚重口音', fine_soft: '纤细轻柔',
  anger: '愤怒', indifference: '冷漠', sarcasm: '嘲讽', sadness: '悲伤', fear: '恐惧', commanding: '命令式',
}

const visualLabels: Record<string, string> = {
  gender_expression: '性别表达', age_expression: '年龄表达', face_shape: '脸型轮廓',
  skin_texture: '皮肤质感', facial_expression: '面部表情', gaze: '眼神与视线',
  lighting: '光影', composition: '构图', background: '背景',
}

const questionPrompts: Record<string, string> = {
  voice_gender: '这个声音像男声、女声，还是不确定或混合？',
  age_sense: '从声音判断，它呈现出怎样的年龄感？',
  pitch_level: '这个声音的音调高低如何？',
  speaking_rate_level: '这个声音的语速快慢如何？',
  timbre: '这个声音是否有明显的口音或特殊音色？',
  emotions: '患者感受到的声音情绪是什么样的？',
  power_level: '这个声音让患者感到多强大？',
  malice_level: '这个声音让患者感到多有恶意？',
}

const levelMeanings: Record<string, string[]> = {
  pitch_level: ['很低', '偏低', '中等', '偏高', '很高'],
  speaking_rate_level: ['很慢', '偏慢', '中等', '偏快', '很快'],
  power_level: ['很弱', '偏弱', '中等', '偏强', '很强'],
  malice_level: ['无恶意', '轻微恶意', '中度恶意', '较强恶意', '很有恶意'],
}

export function DoctorInterviewPage() {
  const { caseId, sessionId } = useParams<{ caseId: string; sessionId: string }>()
  const navigate = useNavigate()
  const { language, t } = useLanguage()
  const [messageApi, messageContext] = message.useMessage()
  const [voiceForm] = Form.useForm<Record<string, unknown>>()
  const [visualForm] = Form.useForm<Record<string, string>>()
  const [contract, setContract] = useState<VoiceFeatureContract | null>(null)
  const [voice, setVoice] = useState<VoiceFeatures | null>(null)
  const [visual, setVisual] = useState<VisualFeatures | null>(null)
  const [avatarVersions, setAvatarVersions] = useState<AvatarVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [restoreSystem, setRestoreSystem] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const knownSafetyEventIds = useRef<Set<number> | null>(null)
  const knownSessionStatus = useRef<PatientSession['status'] | null>(null)
  const safetyRefreshRunning = useRef(false)
  const hasCurrentVisualVersion = Boolean(
    visual
    && avatarVersions.some(
      (version) => version.source_visual_feature_id === visual.visual_feature_id,
    ),
  )

  const loadData = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token || !caseId || !sessionId) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [contractResult, voiceResult, versionResult] = await Promise.all([
        apiRequest<VoiceFeatureContract>('/meta/voice-feature-contract'),
        apiRequest<VoiceFeatures>(`/sessions/${sessionId}/voice-features`, { staffToken: token }),
        apiRequest<AvatarVersionList>(`/cases/${caseId}/avatar-versions`, {
          staffToken: token,
        }),
      ])
      setContract(contractResult)
      setVoice(voiceResult)
      setAvatarVersions(versionResult.items)
      voiceForm.setFieldsValue(voiceResult.answers)
      setQuestionIndex(0)
      try {
        const visualResult = await apiRequest<VisualFeatures>(`/cases/${caseId}/visual-features`, {
          staffToken: token,
        })
        setVisual(visualResult)
        visualForm.setFieldsValue(visualResult.effective_features)
      } catch (visualError) {
        if (!(visualError instanceof ApiClientError && visualError.status === 409)) throw visualError
      }
      setError(null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t('访谈表单加载失败'))
    } finally {
      setLoading(false)
    }
  }, [caseId, navigate, sessionId, t, visualForm, voiceForm])

  useEffect(() => void loadData(), [loadData])

  const loadSafetyState = useCallback(async () => {
    const token = staffTokenStore.get()
    if (
      !token
      || !caseId
      || !sessionId
      || document.visibilityState !== 'visible'
      || safetyRefreshRunning.current
    ) return
    safetyRefreshRunning.current = true
    try {
      const [sessionResult, safetyResult] = await Promise.all([
        apiRequest<PatientSession>(`/sessions/${sessionId}`, { staffToken: token }),
        apiRequest<CaseSafetyEventListResponse>(
          `/cases/safety-events/recent?case_id=${caseId}`,
          { staffToken: token },
        ),
      ])
      const newSafetyEvents = knownSafetyEventIds.current
        ? safetyResult.items.filter(
            (item) => !knownSafetyEventIds.current?.has(item.event_id),
          )
        : []
      const newlyPaused =
        sessionResult.status === 'paused' && knownSessionStatus.current !== 'paused'
      const sensitiveAdjustment = newSafetyEvents.some(
        (item) => item.event_type === 'sensitive_adjustment',
      )
      if (newlyPaused || sensitiveAdjustment) {
        Modal.warning({
          title: t('患者安全提醒'),
          content: t(
            newlyPaused
              ? '患者表示不适，会话已安全暂停，请立即关注。'
              : '系统拦截了一条包含敏感内容的患者调整建议，请及时关注。',
          ),
          okText: t('返回病例'),
          onOk: () => navigate(`/doctor/cases/${caseId}`),
        })
      } else if (
        sessionResult.status === 'ended'
        && knownSessionStatus.current
        && knownSessionStatus.current !== 'ended'
      ) {
        messageApi.info(t('患者会话已结束'))
      }
      knownSessionStatus.current = sessionResult.status
      knownSafetyEventIds.current = new Set(
        safetyResult.items.map((item) => item.event_id),
      )
    } catch (requestError) {
      if (requestError instanceof ApiClientError && requestError.status === 401) {
        staffTokenStore.clear()
        navigate('/doctor/login', { replace: true })
      }
    } finally {
      safetyRefreshRunning.current = false
    }
  }, [caseId, messageApi, navigate, sessionId, t])

  useEffect(() => {
    const refreshVisibleSafety = () => void loadSafetyState()
    void refreshVisibleSafety()
    const timer = window.setInterval(refreshVisibleSafety, 2000)
    window.addEventListener('focus', refreshVisibleSafety)
    document.addEventListener('visibilitychange', refreshVisibleSafety)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refreshVisibleSafety)
      document.removeEventListener('visibilitychange', refreshVisibleSafety)
    }
  }, [loadSafetyState])

  async function saveCurrentQuestion(options?: { advance?: boolean; extract?: boolean }) {
    const token = staffTokenStore.get()
    if (!token || !sessionId || !contract) return false
    const questionKey = contract.question_order[questionIndex]
    let value: unknown
    try {
      const values = await voiceForm.validateFields([questionKey])
      value = values[questionKey] === undefined ? null : values[questionKey]
    } catch {
      return false
    }
    setSaving(true)
    try {
      await apiRequest(`/sessions/${sessionId}/voice-features/${questionKey}`, {
        method: 'PUT',
        staffToken: token,
        idempotencyKey: newIdempotencyKey(`q-${questionKey}`),
        body: { value, source: 'doctor_interview' },
      })
      const refreshed = await apiRequest<VoiceFeatures>(`/sessions/${sessionId}/voice-features`, {
        staffToken: token,
      })
      setVoice(refreshed)
      if (options?.extract) {
        await extractFeatures(token)
      } else if (options?.advance && questionIndex < contract.question_order.length - 1) {
        setQuestionIndex((current) => current + 1)
        messageApi.success(language === 'en' ? `Question ${questionIndex + 1} saved automatically` : `${t('第')} ${questionIndex + 1} ${t('题已自动保存')}`)
      } else {
        messageApi.success(language === 'en' ? `Question ${questionIndex + 1} saved` : `${t('第')} ${questionIndex + 1} ${t('题已保存')}`)
      }
      return true
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('保存失败'))
      return false
    } finally {
      setSaving(false)
    }
  }

  async function extractFeatures(token: string) {
    if (!caseId || !sessionId) return
    try {
      await apiRequest(`/cases/${caseId}/extract-features`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('extract-visual'),
        body: { session_id: sessionId },
      })
      const result = await apiRequest<VisualFeatures>(`/cases/${caseId}/visual-features`, {
        staffToken: token,
      })
      setVisual(result)
      visualForm.setFieldsValue(result.effective_features)
      messageApi.success(t('视觉特征映射已完成，请由医生确认'))
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('映射失败'))
    }
  }

  async function skipOptionalQuestion() {
    if (!contract) return
    const questionKey = contract.question_order[questionIndex]
    if (!contract.optional_nullable_questions.includes(questionKey)) return
    voiceForm.setFieldValue(questionKey, null)
    await saveCurrentQuestion({
      advance: questionIndex < contract.question_order.length - 1,
      extract: questionIndex === contract.question_order.length - 1,
    })
  }

  function renderQuestionInput(questionKey: string) {
    const required = !contract?.optional_nullable_questions.includes(questionKey)
    const rules = required
      ? [{ required: true, message: `${t('请完成')}${t(labels[questionKey])}` }]
      : undefined
    if (questionKey === 'emotions') {
      return (
        <Form.Item name={questionKey} rules={rules}>
          <Checkbox.Group
            aria-label={t(labels[questionKey])}
            options={contract?.enums.emotions.map((value) => ({
              value,
              label: t(enumLabels[value]),
            }))}
          />
        </Form.Item>
      )
    }
    if (levelMeanings[questionKey]) {
      const meanings = levelMeanings[questionKey]
      return (
        <Form.Item name={questionKey} rules={rules}>
          <Slider
            aria-label={t(labels[questionKey])}
            min={1}
            max={5}
            step={1}
            marks={Object.fromEntries(
              meanings.map((meaning, index) => [
                index + 1,
                { label: <span>{index + 1}<small>{t(meaning)}</small></span> },
              ]),
            )}
            tooltip={{
              formatter: (value) =>
                value ? `${value} · ${t(meanings[value - 1])}` : null,
            }}
          />
        </Form.Item>
      )
    }
    const values = contract?.enums[questionKey] ?? []
    return (
      <Form.Item name={questionKey} rules={rules}>
        <Radio.Group
          className="guided-option-grid"
          aria-label={t(labels[questionKey])}
        >
          {values.map((value) => (
            <Radio key={value} value={value}>
              {t(enumLabels[value])}
            </Radio>
          ))}
        </Radio.Group>
      </Form.Item>
    )
  }

  async function confirmVisualFeatures() {
    const token = staffTokenStore.get()
    if (!token || !caseId || !visual) return
    const effective = await visualForm.validateFields()
    setSaving(true)
    try {
      const result = await apiRequest<VisualFeatures>(`/cases/${caseId}/visual-features`, {
        method: 'PUT',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('confirm-visual'),
        body: {
          effective_features: effective,
          restore_system_result: restoreSystem,
          doctor_confirmed: true,
        },
      })
      setVisual(result)
      visualForm.setFieldsValue(result.effective_features)
      setRestoreSystem(false)
      messageApi.success(t('九项视觉特征已由当前医生确认'))
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : t('确认失败'))
    } finally {
      setSaving(false)
    }
  }

  async function generateInitialAvatar() {
    const token = staffTokenStore.get()
    if (
      !token
      || !caseId
      || !visual?.is_doctor_confirmed
      || hasCurrentVisualVersion
      || generating
    ) return
    setGenerating(true)
    try {
      const result = await apiRequest<AvatarVersion>(`/cases/${caseId}/avatar-generations`, {
        method: 'POST',
        staffToken: token,
        idempotencyKey: newIdempotencyKey('interview-avatar-generate'),
        body: { mode: 'initial' },
      })
      setAvatarVersions((current) => [result, ...current])
      messageApi.success(t('生图任务已提交，完成后需要医生审核才会展示给患者'))
    } catch (requestError) {
      messageApi.error(
        requestError instanceof Error ? requestError.message : t('生图任务提交失败'),
      )
    } finally {
      setGenerating(false)
    }
  }

  if (loading) return <div className="route-fallback"><Spin size="large" tip={t('正在恢复访谈草稿…')} /></div>

  const currentQuestionKey = contract?.question_order[questionIndex]
  const currentQuestionRequired = currentQuestionKey
    ? !contract?.optional_nullable_questions.includes(currentQuestionKey)
    : true

  return (
    <div className="interview-page">
      {messageContext}
      <header className="case-page__header">
        <Brand />
        <div className="case-page__header-actions">
          <LanguageSwitcher />
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/doctor/cases/${caseId}`)}>{t('返回病例')}</Button>
        </div>
      </header>
      <main className="interview-page__content">
        <div className="interview-page__heading">
        <div><span className="eyebrow">{t('医生陪同访谈')}</span><h1>{t('记录患者的声音体验')}</h1><p>{t('请结合患者原话与现场观察逐项记录；题目、选项和答案不会显示在患者页面。')}</p></div>
          <Progress type="circle" size={72} percent={Math.round(((voice?.completed_count ?? 0) / 8) * 100)} format={() => `${voice?.completed_count ?? 0}/8`} />
        </div>
        {error && <Alert type="error" showIcon message={error} />}
        <Steps className="interview-steps" current={visual?.is_doctor_confirmed ? 2 : visual ? 1 : 0} items={[{ title: t('结构化访谈') }, { title: t('视觉映射') }, { title: t('医生确认') }]} />

        <Card
          className="interview-card guided-question-card"
          title={<span><SoundOutlined /> {t('问题')} {questionIndex + 1} / 8</span>}
          extra={
            <Space>
              <Tag color={currentQuestionRequired ? 'green' : 'default'}>
                {t(currentQuestionRequired ? '必填' : '选填，可跳过')}
              </Tag>
              <Tag color="green">{t('首轮不执行风险分级')}</Tag>
            </Space>
          }
        >
          <Form form={voiceForm} layout="vertical" requiredMark="optional">
            {currentQuestionKey && (
              <div className="guided-question">
                <span className="guided-question__label">{t(labels[currentQuestionKey])}</span>
                <h2>{t(questionPrompts[currentQuestionKey])}</h2>
                <p>
                  {currentQuestionRequired
                    ? t('请根据当面访谈结果选择；确认后本题会自动保存。')
                    : t('本题为选填；未观察到时可以明确跳过，并保存为“未填写”。')}
                </p>
                {renderQuestionInput(currentQuestionKey)}
              </div>
            )}
            <div className="guided-question__actions">
              <Button
                icon={<ArrowLeftOutlined />}
                disabled={questionIndex === 0}
                onClick={() => setQuestionIndex((current) => Math.max(0, current - 1))}
              >
                {t('上一题')}
              </Button>
              <Space wrap>
                {!currentQuestionRequired && (
                  <Button disabled={saving} onClick={() => void skipOptionalQuestion()}>
                    {t('暂不填写')}
                  </Button>
                )}
                <Button
                  icon={<SaveOutlined />}
                  loading={saving}
                  onClick={() => void saveCurrentQuestion()}
                >
                  {t('保存本题')}
                </Button>
                <Button
                  type="primary"
                  icon={questionIndex === 7 ? <ExperimentOutlined /> : <ArrowRightOutlined />}
                  loading={saving}
                  onClick={() =>
                    void saveCurrentQuestion({
                      advance: questionIndex < 7,
                      extract: questionIndex === 7,
                    })
                  }
                >
                  {t(questionIndex === 7 ? '保存并映射视觉特征' : '确认并继续')}
                </Button>
              </Space>
            </div>
          </Form>
        </Card>

        {visual && (
      <Card className="interview-card visual-confirm-card" title={<span><SafetyCertificateOutlined /> {t('视觉表达方向确认')}</span>} extra={visual.is_doctor_confirmed ? <Tag color="success" icon={<CheckCircleFilled />}>{t('医生已确认')}</Tag> : <Tag color="warning">{t('等待医生确认')}</Tag>}>
            <Alert type="info" showIcon message={t('系统映射不是身份推断')} description={t('以下结果只用于低刺激、虚构和非身份化的视觉表达。修改只能从每个字段的受控选项中选择。')} />
            <Form form={visualForm} layout="vertical" className="visual-form" onValuesChange={() => setRestoreSystem(false)}>
              <Row gutter={[20, 4]}>
                {Object.keys(visual.system_result).map((key) => {
                  const options = Array.from(new Set([visual.system_result[key], ...visual.controlled_options[key]]))
                  return <Col xs={24} md={12} key={key}><Form.Item label={t(visualLabels[key])} name={key} rules={[{ required: true }]}><Select options={options.map((value, index) => ({ value, label: language === 'en' ? (value === visual.system_result[key] ? 'System recommendation' : `Controlled option ${index + 1}`) : t(value) }))} /></Form.Item></Col>
                })}
              </Row>
            </Form>
            <Space className="visual-actions" wrap>
              <Button onClick={() => { visualForm.setFieldsValue(visual.system_result); setRestoreSystem(true) }}>
                {t('恢复系统结果')}
              </Button>
              <Button
                type={visual.is_doctor_confirmed ? 'default' : 'primary'}
                icon={<CheckCircleFilled />}
                loading={saving}
                onClick={() => void confirmVisualFeatures()}
              >
                {t('确认视觉特征')}
              </Button>
              {visual.is_doctor_confirmed && (
                !hasCurrentVisualVersion ? (
                  <Button
                    type="primary"
                    icon={<PictureOutlined />}
                    loading={generating}
                    onClick={() => void generateInitialAvatar()}
                  >
                    {t(generating ? '正在生成图片' : '直接生成图片')}
                  </Button>
                ) : (
                  <Button
                    type="primary"
                    icon={<PictureOutlined />}
                    onClick={() => navigate(`/doctor/cases/${caseId}`)}
                  >
                    {t('查看图片进度')}
                  </Button>
                )
              )}
            </Space>
          </Card>
        )}

        {visual?.is_doctor_confirmed && (
          <Alert
            className="interview-complete"
            type="success"
            showIcon
            message={t('访谈记录与视觉方向已确认')}
            description={t(
              hasCurrentVisualVersion
                ? '图片生成任务已提交。可返回病例页面查看生成进度，完成后进行审核。'
                : '现在可以在本页直接生成第一版视觉表达；后续也可根据患者反馈继续调整。',
            )}
          />
        )}
      </main>
    </div>
  )
}
