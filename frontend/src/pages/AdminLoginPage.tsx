import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { useLanguage } from '../i18n/LanguageProvider'
import { ApiClientError, apiRequest, type LoginResponse, staffTokenStore } from '../lib/api'

export function AdminLoginPage() {
  const navigate = useNavigate()
  const { t } = useLanguage()
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
      if (result.user.role !== 'admin') throw new Error(t('该账户不是管理员账户'))
      staffTokenStore.set(result.access_token)
      navigate('/admin/dashboard', { replace: true })
    } catch (requestError) {
      setError(requestError instanceof ApiClientError ? requestError.message : t('管理员登录失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      surface="admin"
      eyebrow={t('系统管理员')}
      title={t('登录平台管理后台')}
      description={t('管理医护账号、安全规则、平台运行状态、操作审计和数据保留。')}
      asideTitle={t('平台治理不等于查看患者内容')}
      asideItems={[
        t('管理员无法打开病例原文或 Q1-Q8 答案'),
        t('管理员无法查看患者调整原文或 Avatar 图片'),
        t('所有规则修改只影响新的风险校验请求'),
      ]}
    >
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form layout="vertical" requiredMark={false} size="large" onFinish={handleLogin}>
        <Form.Item label={t('管理员邮箱')} name="email" rules={[{ required: true }, { type: 'email' }]}>
          <Input prefix={<MailOutlined />} placeholder="admin@institution.org" />
        </Form.Item>
        <Form.Item label={t('密码')} name="password" rules={[{ required: true }]}>
          <Input.Password prefix={<LockOutlined />} placeholder={t('输入账户密码')} />
        </Form.Item>
        <Button type="primary" htmlType="submit" block className="access-submit" loading={submitting}>
          {t('进入管理后台')}
        </Button>
      </Form>
    </AccessFrame>
  )
}
