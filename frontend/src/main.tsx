import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'

import { App } from './app/App'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
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
          fontFamily:
            'Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", sans-serif',
          controlHeight: 42,
          boxShadowSecondary: '0 18px 45px rgba(30, 66, 56, 0.12)',
        },
        components: {
          Button: { fontWeight: 600, primaryShadow: 'none' },
          Card: { headerBg: 'transparent' },
          Input: { activeShadow: '0 0 0 3px rgba(23, 107, 91, 0.12)' },
          Menu: { itemBorderRadius: 10, itemHeight: 44 },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
)

