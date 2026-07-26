import { Link } from 'react-router-dom'

import { useLanguage } from '../i18n/LanguageProvider'

type BrandProps = {
  compact?: boolean
  inverse?: boolean
}

export function Brand({ compact = false, inverse = false }: BrandProps) {
  const { t } = useLanguage()
  return (
    <Link
      to="/"
      className={`brand ${compact ? 'brand--compact' : ''} ${inverse ? 'brand--inverse' : ''}`}
      aria-label={t('返回首页')}
    >
      <span className="brand__mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="brand__copy">
        <strong>{t('声境 Avatar')}</strong>
        {!compact && <small>{t('幻听治疗支持平台')}</small>}
      </span>
    </Link>
  )
}
