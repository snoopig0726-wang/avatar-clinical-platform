import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckCircleFilled,
  ExperimentOutlined,
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
  Progress,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Steps,
  Tag,
  message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  ApiClientError,
  apiRequest,
  newIdempotencyKey,
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
  const [messageApi, messageContext] = message.useMessage()
  const [voiceForm] = Form.useForm<Record<string, unknown>>()
  const [visualForm] = Form.useForm<Record<string, string>>()
  const [contract, setContract] = useState<VoiceFeatureContract | null>(null)
  const [voice, setVoice] = useState<VoiceFeatures | null>(null)
  const [visual, setVisual] = useState<VisualFeatures | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [restoreSystem, setRestoreSystem] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    const token = staffTokenStore.get()
    if (!token || !caseId || !sessionId) {
      navigate('/doctor/login', { replace: true })
      return
    }
    try {
      const [contractResult, voiceResult] = await Promise.all([
        apiRequest<VoiceFeatureContract>('/meta/voice-feature-contract'),
        apiRequest<VoiceFeatures>(`/cases/${caseId}/voice-features`, { staffToken: token }),
      ])
      setContract(contractResult)
      setVoice(voiceResult)
      voiceForm.setFieldsValue(voiceResult.answers)
      const firstUnanswered = contractResult.question_order.findIndex(
        (key) => !voiceResult.answered_questions.includes(key),
      )
      setQuestionIndex(
        firstUnanswered === -1
          ? contractResult.question_order.length - 1
          : firstUnanswered,
      )
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
      setError(requestError instanceof Error ? requestError.message : '访谈表单加载失败')
    } finally {
      setLoading(false)
    }
  }, [caseId, navigate, sessionId, visualForm, voiceForm])

  useEffect(() => void loadData(), [loadData])

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
      const refreshed = await apiRequest<VoiceFeatures>(`/cases/${caseId}/voice-features`, {
        staffToken: token,
      })
      setVoice(refreshed)
      if (options?.extract) {
        await extractFeatures(token)
      } else if (options?.advance && questionIndex < contract.question_order.length - 1) {
        setQuestionIndex((current) => current + 1)
        messageApi.success(`第 ${questionIndex + 1} 题已自动保存`)
      } else {
        messageApi.success(`第 ${questionIndex + 1} 题已保存`)
      }
      return true
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '保存失败')
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
      messageApi.success('视觉特征映射已完成，请由医生确认')
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '映射失败')
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
      ? [{ required: true, message: `请完成${labels[questionKey]}` }]
      : undefined
    if (questionKey === 'emotions') {
      return (
        <Form.Item name={questionKey} rules={rules}>
          <Checkbox.Group
            options={contract?.enums.emotions.map((value) => ({
              value,
              label: enumLabels[value],
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
            min={1}
            max={5}
            step={1}
            marks={Object.fromEntries(
              meanings.map((meaning, index) => [
                index + 1,
                { label: <span>{index + 1}<small>{meaning}</small></span> },
              ]),
            )}
            tooltip={{
              formatter: (value) =>
                value ? `${value} 档 · ${meanings[value - 1]}` : null,
            }}
          />
        </Form.Item>
      )
    }
    const values = contract?.enums[questionKey] ?? []
    return (
      <Form.Item name={questionKey} rules={rules}>
        <Select
          allowClear={!required}
          placeholder={required ? '请选择' : '未填写'}
          options={values.map((value) => ({ value, label: enumLabels[value] }))}
        />
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
      messageApi.success('九项视觉特征已由当前医生确认')
    } catch (requestError) {
      messageApi.error(requestError instanceof Error ? requestError.message : '确认失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="route-fallback"><Spin size="large" tip="正在恢复访谈草稿…" /></div>

  const currentQuestionKey = contract?.question_order[questionIndex]
  const currentQuestionRequired = currentQuestionKey
    ? !contract?.optional_nullable_questions.includes(currentQuestionKey)
    : true

  return (
    <div className="interview-page">
      {messageContext}
      <header className="case-page__header">
        <Brand />
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/doctor/cases/${caseId}`)}>返回病例</Button>
      </header>
      <main className="interview-page__content">
        <div className="interview-page__heading">
          <div><span className="eyebrow">医生当面访谈</span><h1>Q1–Q8 声音特征录入</h1><p>所有内容仅由医生录入，患者页面不会显示题目、选项或答案。</p></div>
          <Progress type="circle" size={72} percent={Math.round(((voice?.completed_count ?? 0) / 8) * 100)} format={() => `${voice?.completed_count ?? 0}/8`} />
        </div>
        {error && <Alert type="error" showIcon message={error} />}
        <Steps className="interview-steps" current={visual?.is_doctor_confirmed ? 2 : visual ? 1 : 0} items={[{ title: '结构化访谈' }, { title: '视觉映射' }, { title: '医生确认' }]} />

        <Card
          className="interview-card guided-question-card"
          title={<span><SoundOutlined /> 问题 {questionIndex + 1} / 8</span>}
          extra={
            <Space>
              <Tag color={currentQuestionRequired ? 'green' : 'default'}>
                {currentQuestionRequired ? '必填' : '选填，可跳过'}
              </Tag>
              <Tag color="green">首轮不执行风险分级</Tag>
            </Space>
          }
        >
          <Form form={voiceForm} layout="vertical" requiredMark="optional">
            {currentQuestionKey && (
              <div className="guided-question">
                <span className="guided-question__label">{labels[currentQuestionKey]}</span>
                <h2>{questionPrompts[currentQuestionKey]}</h2>
                <p>
                  {currentQuestionRequired
                    ? '请根据当面访谈结果选择；确认后本题会自动保存。'
                    : '本题为选填；未观察到时可以明确跳过，并保存为“未填写”。'}
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
                上一题
              </Button>
              <Space wrap>
                {!currentQuestionRequired && (
                  <Button disabled={saving} onClick={() => void skipOptionalQuestion()}>
                    暂不填写
                  </Button>
                )}
                <Button
                  icon={<SaveOutlined />}
                  loading={saving}
                  onClick={() => void saveCurrentQuestion()}
                >
                  保存本题
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
                  {questionIndex === 7 ? '保存并映射视觉特征' : '确认并继续'}
                </Button>
              </Space>
            </div>
          </Form>
        </Card>

        {visual && (
          <Card className="interview-card visual-confirm-card" title={<span><SafetyCertificateOutlined /> 九项视觉特征确认</span>} extra={visual.is_doctor_confirmed ? <Tag color="success" icon={<CheckCircleFilled />}>医生已确认</Tag> : <Tag color="warning">等待医生确认</Tag>}>
            <Alert type="info" showIcon message="系统映射不是身份推断" description="以下结果只用于低刺激、虚构和非身份化的视觉表达。修改只能从每个字段的受控选项中选择。" />
            <Form form={visualForm} layout="vertical" className="visual-form" onValuesChange={() => setRestoreSystem(false)}>
              <Row gutter={[20, 4]}>
                {Object.keys(visual.system_result).map((key) => {
                  const options = Array.from(new Set([visual.system_result[key], ...visual.controlled_options[key]]))
                  return <Col xs={24} md={12} key={key}><Form.Item label={visualLabels[key]} name={key} rules={[{ required: true }]}><Select options={options.map((value) => ({ value, label: value }))} /></Form.Item></Col>
                })}
              </Row>
            </Form>
            {visual.mapping_explanation.safety_rules_applied.length > 0 && <Alert type="success" showIcon message="已应用自动柔和规则" description={visual.mapping_explanation.safety_rules_applied.join('；')} />}
            <Space className="visual-actions"><Button onClick={() => { visualForm.setFieldsValue(visual.system_result); setRestoreSystem(true) }}>恢复系统结果</Button><Button type="primary" icon={<CheckCircleFilled />} loading={saving} onClick={() => void confirmVisualFeatures()}>确认视觉特征</Button></Space>
          </Card>
        )}

        {visual?.is_doctor_confirmed && <Alert className="interview-complete" type="success" showIcon message="表单和视觉特征确认已完成" description="统一 Prompt 构建门禁已经满足；请返回病例页面发起首版生成或按相同特征重新生成。" />}
      </main>
    </div>
  )
}
