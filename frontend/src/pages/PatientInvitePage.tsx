import { KeyOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
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
          : '邀请码验证失败，请联系现场医生',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow="受邀患者入口"
      title="使用邀请码进入会话"
      description="邀请码由现场医生提供，仅用于当前设备上的一次受监督会话。"
      asideTitle="这是一次由医生陪同的受控查看"
      asideItems={[
        '无需注册账户，也不需要填写姓名或邮箱',
        '只能查看医生审核并授权的当前 Avatar',
        '如感到不适，可以随时触发安全暂停',
      ]}
    >
      <Alert
        className="access-alert"
        type="success"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="请在现场医生陪同下继续"
        description="系统不会要求你提供姓名、身份证号、联系方式或住址。"
      />
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form
        layout="vertical"
        requiredMark={false}
        size="large"
        onFinish={handleRedeem}
      >
        <Form.Item
          label="一次性邀请码"
          name="inviteCode"
          extra="邀请码有效期为 24 小时，且只能兑换一次。"
          rules={[
            { required: true, message: '请输入现场医生提供的邀请码' },
            { min: 6, message: '请检查邀请码是否完整' },
          ]}
        >
          <Input
            className="invite-input"
            prefix={<KeyOutlined />}
            placeholder="例如：A7K9-P2Q4"
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
          验证并进入会话
        </Button>
      </Form>
      <p className="access-secondary">邀请码无效、过期或已使用时，请联系现场医生重新获取。</p>
    </AccessFrame>
  )
}
