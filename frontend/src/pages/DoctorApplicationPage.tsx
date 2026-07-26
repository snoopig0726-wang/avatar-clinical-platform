import {
  CheckCircleOutlined,
  LockOutlined,
  MailOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Alert, Button, Form, Input, Result } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AccessFrame } from '../components/AccessFrame'
import { useLanguage } from '../i18n/LanguageProvider'
import {
  ApiClientError,
  apiRequest,
  type DoctorApplicationResponse,
  newIdempotencyKey,
  type VerifyEmailResponse,
} from '../lib/api'

type ApplicationValues = {
  display_name: string
  email: string
  password: string
  confirm_password: string
}

export function DoctorApplicationPage() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [application, setApplication] = useState<DoctorApplicationResponse | null>(null)
  const [verified, setVerified] = useState(false)

  async function submitApplication(values: ApplicationValues) {
    setSubmitting(true)
    setError(null)
    try {
      const result = await apiRequest<DoctorApplicationResponse>(
        '/auth/doctor-applications',
        {
          method: 'POST',
          idempotencyKey: newIdempotencyKey('doctor-application'),
          body: {
            display_name: values.display_name,
            email: values.email,
            password: values.password,
          },
        },
      )
      setApplication(result)
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError
          ? requestError.message
          : t('账户申请暂时无法提交'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function verifyDevelopmentEmail() {
    if (!application?.development_verification_token) return
    setSubmitting(true)
    setError(null)
    try {
      await apiRequest<VerifyEmailResponse>('/auth/verify-email', {
        method: 'POST',
        idempotencyKey: newIdempotencyKey('doctor-email-verification'),
        body: { token: application.development_verification_token },
      })
      setVerified(true)
    } catch (requestError) {
      setError(
        requestError instanceof ApiClientError
          ? requestError.message
          : t('邮箱验证暂时无法完成'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow={t('医护账户申请')}
      title={t('申请医护工作台账户')}
      description={t('仅向经过机构验证和管理员审批的专业人员开放。')}
      asideTitle={t('只让经过验证的专业人员进入')}
      asideItems={[
        t('机构邮箱用于确认专业身份与申请来源'),
        t('管理员审批通过后才能访问患者相关工作'),
        t('账户停用后，现有登录会话会立即失效'),
      ]}
    >
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      {verified ? (
        <Result
          status="success"
          icon={<CheckCircleOutlined />}
          title={t('机构邮箱验证完成')}
          subTitle={t('账户正在等待管理员审批。审批通过后即可使用申请时设置的密码登录。')}
          extra={
            <Button type="primary" onClick={() => navigate('/doctor/login')}>
              {t('返回医生登录')}
            </Button>
          }
        />
      ) : application ? (
        <>
          <Alert
            className="access-alert"
            type="success"
            showIcon
            message={t('账户申请已创建')}
            description={application.message}
          />
          {application.development_verification_token ? (
            <>
              <Alert
                className="access-alert"
                type="warning"
                showIcon
                message={t('本地开发验证')}
                description={t('当前未连接机构邮件服务。此按钮仅在本地开发环境出现，用于验证完整审批流程。')}
              />
              <Button
                type="primary"
                block
                className="access-submit"
                loading={submitting}
                onClick={() => void verifyDevelopmentEmail()}
              >
                {t('完成本地邮箱验证')}
              </Button>
            </>
          ) : (
            <Alert
              className="access-alert"
              type="info"
              showIcon
              message={t('等待机构邮箱验证')}
              description={t('请按照机构发送的验证通知继续；验证完成后账户将进入管理员审批队列。')}
            />
          )}
          <p className="access-secondary">
            {t('已完成申请？')}<Button type="link" onClick={() => navigate('/doctor/login')}>{t('返回登录')}</Button>
          </p>
        </>
      ) : (
        <Form
          layout="vertical"
          requiredMark={false}
          size="large"
          onFinish={(values) => void submitApplication(values)}
        >
          <Form.Item
            name="display_name"
            label={t('医生姓名')}
            rules={[
              { required: true, message: t('请输入医生姓名') },
              { min: 2, max: 100, message: t('姓名长度应为 2–100 个字符') },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('用于工作台和审核记录')} />
          </Form.Item>
          <Form.Item
            name="email"
            label={t('机构邮箱')}
            rules={[
              { required: true, message: t('请输入机构邮箱') },
              { type: 'email', message: t('请输入有效的邮箱地址') },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="name@institution.org" />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('设置密码')}
            rules={[
              { required: true, message: t('请设置账户密码') },
              { min: 12, message: t('密码至少需要 12 个字符') },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('至少 12 个字符')}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label={t('确认密码')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('请再次输入密码') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('两次输入的密码不一致')))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('再次输入密码')}
              autoComplete="new-password"
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            className="access-submit"
            loading={submitting}
          >
            {t('提交账户申请')}
          </Button>
          <p className="access-secondary">
            {t('已有账户？')}<Button type="link" onClick={() => navigate('/doctor/login')}>{t('返回登录')}</Button>
          </p>
        </Form>
      )}
    </AccessFrame>
  )
}
