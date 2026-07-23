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
          : '账户申请暂时无法提交',
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
          : '邮箱验证暂时无法完成',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AccessFrame
      eyebrow="医生账户申请"
      title="申请临床研究工作台权限"
      description="医生账户需要完成机构邮箱验证，并由系统管理员审批后才能登录。"
      asideTitle="账户权限采用双重门禁"
      asideItems={[
        '机构邮箱验证确认申请来源',
        '管理员审批后才开放医生工作台',
        '账户停用会立即撤销现有登录会话',
      ]}
    >
      {error && <Alert className="access-alert" type="error" showIcon message={error} />}
      {verified ? (
        <Result
          status="success"
          icon={<CheckCircleOutlined />}
          title="机构邮箱验证完成"
          subTitle="账户正在等待管理员审批。审批通过后即可使用申请时设置的密码登录。"
          extra={
            <Button type="primary" onClick={() => navigate('/doctor/login')}>
              返回医生登录
            </Button>
          }
        />
      ) : application ? (
        <>
          <Alert
            className="access-alert"
            type="success"
            showIcon
            message="账户申请已创建"
            description={application.message}
          />
          {application.development_verification_token ? (
            <>
              <Alert
                className="access-alert"
                type="warning"
                showIcon
                message="本地开发验证"
                description="当前未连接机构邮件服务。此按钮仅在本地开发环境出现，用于验证完整审批流程。"
              />
              <Button
                type="primary"
                block
                className="access-submit"
                loading={submitting}
                onClick={() => void verifyDevelopmentEmail()}
              >
                完成本地邮箱验证
              </Button>
            </>
          ) : (
            <Alert
              className="access-alert"
              type="info"
              showIcon
              message="等待机构邮箱验证"
              description="请按照机构发送的验证通知继续；验证完成后账户将进入管理员审批队列。"
            />
          )}
          <p className="access-secondary">
            已完成申请？<Button type="link" onClick={() => navigate('/doctor/login')}>返回登录</Button>
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
            label="医生姓名"
            rules={[
              { required: true, message: '请输入医生姓名' },
              { min: 2, max: 100, message: '姓名长度应为 2–100 个字符' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用于工作台和审核记录" />
          </Form.Item>
          <Form.Item
            name="email"
            label="机构邮箱"
            rules={[
              { required: true, message: '请输入机构邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="name@institution.org" />
          </Form.Item>
          <Form.Item
            name="password"
            label="设置密码"
            rules={[
              { required: true, message: '请设置账户密码' },
              { min: 12, message: '密码至少需要 12 个字符' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="至少 12 个字符"
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="再次输入密码"
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
            提交账户申请
          </Button>
          <p className="access-secondary">
            已有账户？<Button type="link" onClick={() => navigate('/doctor/login')}>返回登录</Button>
          </p>
        </Form>
      )}
    </AccessFrame>
  )
}
