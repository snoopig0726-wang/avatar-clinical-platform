import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <main className="result-page">
      <Result
        status="404"
        title="页面不存在或无权访问"
        subTitle="为保护病例隐私，系统不会确认该资源是否存在。"
        extra={
          <Button type="primary" onClick={() => navigate('/')}>
            返回首页
          </Button>
        }
      />
    </main>
  )
}

