import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { useLanguage } from '../i18n/LanguageProvider'
import { ApiClientError, apiRequest, type LoginResponse, staffTokenStore } from '../lib/api'

export function DoctorLoginPage() {
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
      if (result.user.role !== 'doctor') throw new Error(t('该账户不是医生账户'))
      staffTokenStore.set(result.access_token)
      navigate('/doctor/workspace', { replace: true })
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError ? requestError.message : t('登录失败，请检查账户信息'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow={t('医护人员入口')}
      title={t('登录医护工作台')}
      description={t('继续管理患者会话、记录声音体验，并审核用于医患沟通的视觉表达。')}
      asideTitle={t('把患者感受转化为可讨论的治疗线索')}
      asideItems={[
        t('通过结构化访谈，帮助患者更清楚地表达声音体验'),
        t('结合患者反馈，持续观察症状与生活影响的变化'),
        t('所有图像均需经过安全检查和医生确认后再展示'),
      ]}
    >
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      <Form
        layout="vertical"
        requiredMark={false}
        onFinish={handleLogin}
        size="large"
      >
        <Form.Item
          label={t('机构邮箱')}
          name="email"
          rules={[
            { required: true, message: t('请输入机构邮箱') },
            { type: 'email', message: t('请输入有效的邮箱地址') },
          ]}
        >
          <Input prefix={<MailOutlined />} placeholder="name@institution.org" autoComplete="email" />
        </Form.Item>
        <Form.Item
          label={t('密码')}
          name="password"
          rules={[{ required: true, message: t('请输入密码') }]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder={t('输入账户密码')}
            autoComplete="current-password"
          />
        </Form.Item>
        <div className="form-between">
          <Checkbox>{t('保持本设备登录')}</Checkbox>
          <Button type="link" className="inline-button">
            {t('无法登录？')}
          </Button>
        </div>
        <Button
          type="primary"
          htmlType="submit"
          block
          className="access-submit"
          loading={submitting}
        >
          {t('进入工作台')}
        </Button>
      </Form>
      <p className="access-secondary">
        {t('还没有机构账户？')}
        <Button type="link" onClick={() => navigate('/doctor/apply')}>
          {t('申请医生账户')}
        </Button>
      </p>
    </AccessFrame>
  )
}
