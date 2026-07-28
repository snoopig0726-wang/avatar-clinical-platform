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
          colorPrimary: '#245c52',
          colorInfo: '#34766a',
          colorSuccess: '#34766a',
          colorWarning: '#b7791f',
          colorError: '#a63d3d',
          colorText: '#183b35',
          colorTextSecondary: '#66756f',
          colorBorder: '#cbd8d2',
          colorBgBase: '#f7f4ed',
          colorBgContainer: '#fcfbf7',
          borderRadius: 6,
          borderRadiusLG: 16,
          fontSize: 16,
          fontSizeLG: 18,
          fontSizeSM: 14,
          lineHeight: 1.55,
          fontFamily:
            '"Noto Sans SC", "Source Han Sans SC", Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
          controlHeight: 44,
          controlHeightLG: 48,
          boxShadowSecondary: '0 8px 24px rgba(24, 59, 53, 0.08)',
        },
        components: {
          Button: {
            borderRadius: 6,
            controlHeight: 44,
            controlHeightLG: 48,
            fontWeight: 600,
            primaryShadow: 'none',
          },
          Card: {
            borderRadiusLG: 16,
            headerBg: 'transparent',
            headerFontSize: 18,
            paddingLG: 24,
          },
          Input: {
            borderRadius: 6,
            activeShadow: '0 0 0 3px #b8d8d0',
          },
          Select: {
            borderRadius: 6,
            activeOutlineColor: '#b8d8d0',
            optionHeight: 44,
          },
          Menu: { itemBorderRadius: 6, itemHeight: 44 },
          Modal: { borderRadiusLG: 16 },
          Table: { headerBg: '#eef3f0', rowHoverBg: '#f3f7f4' },
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
