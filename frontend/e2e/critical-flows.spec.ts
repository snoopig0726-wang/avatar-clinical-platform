import { expect, test, type Page } from '@playwright/test'

test.beforeEach(async ({ page }, testInfo) => {
  if (!testInfo.title.includes('language switcher')) {
    await page.addInitScript(() => window.localStorage.setItem('avatar-language', 'zh-CN'))
  }
})

async function loginDoctor(page: Page) {
  await page.goto('/doctor/login')
  await page.getByLabel('机构邮箱').fill('doctor@example.com')
  await page.getByLabel('密码').fill('Avatar-demo-2026')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL(/\/doctor\/workspace$/, { timeout: 20_000 })
}

test('public entry points explain the patient and professional paths', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /让你的声音被理解/ })).toBeVisible()
  await expect(page.getByText(/不能保证治愈/)).toBeVisible()

  await page.getByRole('button', { name: '医护人员登录' }).click()
  await expect(page.getByRole('heading', { name: '登录医护工作台' })).toBeVisible()
  await page.getByRole('button', { name: '申请医生账户' }).click()
  await expect(page.getByRole('heading', { name: '申请医护工作台账户' })).toBeVisible()

  await page.goto('/patient/invite')
  await expect(page.getByRole('heading', { name: '输入邀请码，进入你的会话' })).toBeVisible()
  await expect(page.getByText('Q1 · 声音性别感')).not.toBeVisible()
  await expect(page.getByText('患者账户登录')).not.toBeVisible()
})

test('language switcher defaults to English and persists all three choices', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: /Make your voice understood/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'English' })).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('button', { name: '简体中文' }).click()
  await expect(page.getByRole('heading', { name: /让你的声音被理解/ })).toBeVisible()

  await page.getByRole('button', { name: '繁體中文' }).click()
  await expect(page.getByRole('heading', { name: /讓你的聲音被理解/ })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '繁體中文' })).toHaveAttribute('aria-pressed', 'true')
})

test('approved demo doctor can enter the isolated workspace', async ({ page }) => {
  await loginDoctor(page)
  await expect(page.getByText(/优先处理待审核图像和进行中会话/)).toBeVisible()
  await expect(page.getByText('今日工作提醒', { exact: true })).toBeVisible()
  await expect(page.getByText('患者安全与授权', { exact: true })).toBeVisible()
  await expect(page.getByLabel('搜索预约号')).toBeVisible()
  await expect(page.locator('.cases-card .ant-pagination')).toBeVisible()
  await page.getByRole('button', { name: '创建匿名病例' }).click()
  await expect(page.getByText('填写固定预约号，不得填写姓名、联系方式')).toBeVisible()
  await expect(page.getByPlaceholder('例如 APPT-2026-0001')).toBeVisible()
  await page.keyboard.press('Escape')
})

test('protected staff pages reject missing role credentials', async ({ page }) => {
  await page.goto('/doctor/workspace')
  await expect(page).toHaveURL(/\/doctor\/login$/)

  await page.goto('/admin/dashboard')
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('doctor interview exposes one guided question at a time', async ({ page }) => {
  await loginDoctor(page)
  await page.getByLabel('搜索预约号').fill('DEMO-VOICE-001')
  await page.getByLabel('搜索预约号').press('Enter')
  const matchingCase = page.locator('.case-id-cell--button').filter({ hasText: 'DEMO-VOICE-001' })
  await expect(matchingCase).toBeVisible()
  await expect(page.locator('.cases-card .ant-spin-spinning')).toHaveCount(0)
  await matchingCase.click()
  await expect(page.getByRole('heading', { name: 'DEMO-VOICE-001' })).toBeVisible({
    timeout: 15_000,
  })
  const caseId = page.url().split('/').at(-1)!
  const apiBase = process.env.E2E_API_BASE ?? '/api'
  const sessionId = await page.evaluate(
    async ({ targetCaseId, targetApiBase }) => {
      const token = window.sessionStorage.getItem('avatar.staff_token')
      const response = await window.fetch(
        `${targetApiBase}/cases/${targetCaseId}/session-invites`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      )
      const payload = await response.json()
      return payload.items.find((item: { session_id: string | null }) => item.session_id)?.session_id
    },
    { targetCaseId: caseId, targetApiBase: apiBase },
  )
  expect(sessionId).toBeTruthy()
  await page.goto(`/doctor/cases/${caseId}/interview/${sessionId}`)

  await expect(page.locator('.guided-question-card')).toBeVisible({ timeout: 20_000 })
  await expect(
    page.getByRole('heading', { name: '这个声音像男声、女声，还是不确定或混合？' }),
  ).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('这个声音让患者感到多有恶意？')).not.toBeVisible()
  await expect(page.getByText(/题目、选项和答案不会显示在患者页面/)).toBeVisible()
})

test('administrator sees scoped management operations', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByLabel('管理员邮箱').fill('admin@example.com')
  await page.getByLabel('密码').fill('Avatar-admin-2026')
  await page.getByRole('button', { name: '进入管理后台' }).click()

  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.getByRole('heading', { name: '安全、权限与运行状态' })).toBeVisible()
  await expect(page.getByRole('tab', { name: /医护账号/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /安全规则/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /操作审计/ })).toBeVisible()
  await page.getByRole('tab', { name: /数据保留/ }).click()
  await expect(page.getByLabel('搜索预约号')).toBeVisible()
})

test('mobile public surfaces do not overflow the viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')

  for (const path of ['/', '/patient/invite', '/doctor/login', '/admin/login']) {
    await page.goto(path)
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
      )
      .toBe(true)
  }
})
