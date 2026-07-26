import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import enUS from 'antd/locale/en_US'
import zhCN from 'antd/locale/zh_CN'
import zhTW from 'antd/locale/zh_TW'
import { BrowserRouter } from 'react-router-dom'

import { App } from './app/App'
import { LanguageProvider, useLanguage } from './i18n/LanguageProvider'
import './styles/global.css'

function LocalizedApplication() {
  const { language } = useLanguage()
  const locale = language === 'zh-CN' ? zhCN : language === 'zh-TW' ? zhTW : enUS

  return (
    <ConfigProvider
      locale={locale}
      theme={{
        token: {
          colorPrimary: '#176b5b',
          colorInfo: '#176b5b',
          colorSuccess: '#3f7f63',
          colorWarning: '#b47a30',
          colorError: '#b84b4b',
          colorText: '#19322d',
          colorTextSecondary: '#62736e',
          colorBgBase: '#f6f8f7',
          borderRadius: 12,
          borderRadiusLG: 18,
          fontSize: 16,
          fontSizeLG: 18,
          fontSizeSM: 14,
          lineHeight: 1.6,
          fontFamily:
            'Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif',
          controlHeight: 48,
          controlHeightLG: 54,
          boxShadowSecondary: '0 18px 45px rgba(30, 66, 56, 0.12)',
        },
        components: {
          Button: { fontWeight: 600, primaryShadow: 'none' },
          Card: { headerBg: 'transparent', headerFontSize: 18 },
          Input: { activeShadow: '0 0 0 3px rgba(23, 107, 91, 0.12)' },
          Menu: { itemBorderRadius: 10, itemHeight: 48 },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LanguageProvider>
      <LocalizedApplication />
    </LanguageProvider>
  </React.StrictMode>,
)
