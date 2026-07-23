import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { ApiClientError, apiRequest, type LoginResponse, staffTokenStore } from '../lib/api'

export function AdminLoginPage() {
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
      if (result.user.role !== 'admin') throw new Error('该账户不是管理员账户')
      staffTokenStore.set(result.access_token)
      navigate('/admin/dashboard', { replace: true })
    } catch (requestError) {
      setError(requestError instanceof ApiClientError ? requestError.message : '管理员登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow="系统管理员"
      title="登录独立管理后台"
      description="管理员只处理工作人员账户、规则、聚合统计、脱敏审计和归档恢复。"
      asideTitle="管理权限与病例内容严格隔离"
      asideItems={[
        '管理员无法打开病例原文或 Q1-Q8 答案',
        '管理员无法查看患者调整原文或 Avatar 图片',
        '所有规则修改只影响新的风险校验请求',
      ]}
    >
      <Alert
        className="access-alert"
        type="warning"
        showIcon
        message="受限管理入口"
        description="越权访问与敏感字段请求将被拒绝并记录。"
      />
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form layout="vertical" requiredMark={false} size="large" onFinish={handleLogin}>
        <Form.Item label="管理员邮箱" name="email" rules={[{ required: true }, { type: 'email' }]}>
          <Input prefix={<MailOutlined />} placeholder="admin@institution.org" />
        </Form.Item>
        <Form.Item label="密码" name="password" rules={[{ required: true }]}>
          <Input.Password prefix={<LockOutlined />} placeholder="输入账户密码" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block className="access-submit" loading={submitting}>
          进入管理后台
        </Button>
      </Form>
    </AccessFrame>
  )
}
