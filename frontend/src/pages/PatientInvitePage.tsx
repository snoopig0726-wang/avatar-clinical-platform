import { KeyOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  getOrCreateDeviceBinding,
  newIdempotencyKey,
  setPatientSession,
} from '../lib/api'

type RedeemResponse = {
  session_id: string
  patient_session_token: string
}

export function PatientInvitePage() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleRedeem(values: { inviteCode: string }) {
    setSubmitting(true)
    setError(null)
    try {
      const result = await apiRequest<RedeemResponse>('/session-invites/redeem', {
        method: 'POST',
        idempotencyKey: newIdempotencyKey('redeem'),
        body: { code: values.inviteCode, device_binding: getOrCreateDeviceBinding() },
      })
      setPatientSession(result.session_id, result.patient_session_token)
      navigate(`/patient/session/${result.session_id}`, { replace: true })
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError
          ? requestError.message
          : t('邀请码验证失败，请联系现场医生'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      surface="patient"
      eyebrow={t('患者入口')}
      title={t('输入邀请码，进入你的会话')}
      description={t('请使用医生提供的一次性邀请码。进入后，医生会陪你一起查看和讨论声音体验。')}
      asideTitle={t('你可以安心表达，我们一起理解')}
      asideItems={[
        t('无需注册账户，也不用填写姓名、邮箱或联系方式'),
        t('页面只会展示医生已经检查并确认的内容'),
        t('任何时候感到不舒服，都可以立即暂停并告诉医生'),
      ]}
      asideImage="/images/patient-clinician-conversation.png"
      asideImagePosition="62% center"
    >
      <Alert
        className="access-alert"
        type="success"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message={t('请让医生陪在你身边')}
        description={t('你不需要独自完成，也不必提供任何身份信息。')}
      />
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form
        layout="vertical"
        requiredMark={false}
        size="large"
        onFinish={handleRedeem}
      >
        <Form.Item
          label={t('医生提供的邀请码')}
          name="inviteCode"
          extra={t('每个邀请码只能使用一次；如果无法进入，请直接告诉身边的医生。')}
          rules={[
            { required: true, message: t('请输入现场医生提供的邀请码') },
            { min: 6, message: t('请检查邀请码是否完整') },
          ]}
        >
          <Input
            className="invite-input"
            prefix={<KeyOutlined />}
            placeholder={t('例如：A7K9-P2Q4')}
            maxLength={16}
            autoComplete="one-time-code"
          />
        </Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          block
          className="access-submit"
          loading={submitting}
        >
          {t('进入我的会话')}
        </Button>
      </Form>
      <p className="access-secondary">{t('邀请码无效、过期或已使用时，请让医生重新创建。')}</p>
    </AccessFrame>
  )
}
