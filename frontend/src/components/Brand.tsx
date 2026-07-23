import { Link } from 'react-router-dom'

type BrandProps = {
  compact?: boolean
  inverse?: boolean
}

export function Brand({ compact = false, inverse = false }: BrandProps) {
  return (
    <Link
      to="/"
      className={`brand ${compact ? 'brand--compact' : ''} ${inverse ? 'brand--inverse' : ''}`}
      aria-label="返回声境 Avatar 首页"
    >
      <span className="brand__mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="brand__copy">
        <strong>声境 Avatar</strong>
        {!compact && <small>临床研究工作台</small>}
      </span>
    </Link>
  )
}

