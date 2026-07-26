import { GlobalOutlined } from '@ant-design/icons'

import { useLanguage, type Language } from '../i18n/LanguageProvider'

const options: Array<{ value: Language; label: string; short: string }> = [
  { value: 'en', label: 'English', short: 'EN' },
  { value: 'zh-CN', label: '简体中文', short: '简' },
  { value: 'zh-TW', label: '繁體中文', short: '繁' },
]

export function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="language-switcher" role="group" aria-label="Language">
      <GlobalOutlined aria-hidden="true" />
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={language === option.value ? 'is-active' : undefined}
          aria-pressed={language === option.value}
          aria-label={option.label}
          onClick={() => setLanguage(option.value)}
        >
          <span className="language-switcher__full">{option.label}</span>
          <span className="language-switcher__short">{option.short}</span>
        </button>
      ))}
    </div>
  )
}
