import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { ApiClientError, apiRequest, type LoginResponse, staffTokenStore } from '../lib/api'

export function DoctorLoginPage() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleLogin(values: { email: string; password: string }) {
    setSubmitting(true)
    setError(null)
    try {
      const result = await apiRequest<LoginResponse>('/auth/login', {
        method: 'POST',
        body: values,
      })
      if (result.user.role !== 'doctor') throw new Error('该账户不是医生账户')
      staffTokenStore.set(result.access_token)
      navigate('/doctor/workspace', { replace: true })
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError ? requestError.message : '登录失败，请检查账户信息',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow="医生入口"
      title="登录临床研究工作台"
      description="请使用已经完成邮箱验证并通过管理员审批的机构账户。"
      asideTitle="将生成过程置于专业判断之下"
      asideItems={[
        'Q1-Q8 仅由医生在当面访谈中录入',
        '候选图片必须经过安全检查和人工审核',
        '只有明确授权的版本才会向患者展示',
      ]}
    >
      <Alert
        className="access-alert"
        type="info"
        showIcon
        message="内部研究系统"
        description="所有访问和关键操作均会记录脱敏审计事件。"
      />
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form
        layout="vertical"
        requiredMark={false}
        onFinish={handleLogin}
        size="large"
      >
        <Form.Item
          label="机构邮箱"
          name="email"
          rules={[
            { required: true, message: '请输入机构邮箱' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input prefix={<MailOutlined />} placeholder="name@institution.org" autoComplete="email" />
        </Form.Item>
        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, message: '请输入密码' }]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="输入账户密码"
            autoComplete="current-password"
          />
        </Form.Item>
        <div className="form-between">
          <Checkbox>保持本设备登录</Checkbox>
          <Button type="link" className="inline-button">
            无法登录？
          </Button>
        </div>
        <Button
          type="primary"
          htmlType="submit"
          block
          className="access-submit"
          loading={submitting}
        >
          进入工作台
        </Button>
      </Form>
      <p className="access-secondary">
        还没有机构账户？
        <Button type="link" onClick={() => navigate('/doctor/apply')}>
          申请医生账户
        </Button>
      </p>
    </AccessFrame>
  )
}
