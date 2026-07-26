import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../i18n/LanguageProvider'

export function NotFoundPage() {
  const navigate = useNavigate()
  const { t } = useLanguage()

  return (
    <main className="result-page">
      <div className="result-page__language"><LanguageSwitcher /></div>
      <Result
        status="404"
        title={t('页面不存在或无权访问')}
        subTitle={t('为保护病例隐私，系统不会确认该资源是否存在。')}
        extra={
          <Button type="primary" onClick={() => navigate('/')}>
            {t('返回首页')}
          </Button>
        }
      />
    </main>
  )
}
