import { expect, test, type Page } from '@playwright/test'

async function loginDoctor(page: Page) {
  await page.goto('/doctor/login')
  await page.getByLabel('机构邮箱').fill('doctor@example.com')
  await page.getByLabel('密码').fill('Avatar-demo-2026')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL(/\/doctor\/workspace$/)
}

test('public entry points expose the clinical safety boundaries', async ({ page }) => {
  await page.goto('/')
  await expect(
    page.getByRole('heading', { name: /将难以言说的声音体验/ }),
  ).toBeVisible()
  await expect(page.getByText('非诊断、非真实身份复刻')).toBeVisible()

  await page.getByRole('button', { name: '医生进入工作台' }).click()
  await expect(
    page.getByRole('heading', { name: '登录临床研究工作台' }),
  ).toBeVisible()
  await page.getByRole('button', { name: '申请医生账户' }).click()
  await expect(
    page.getByRole('heading', { name: '申请临床研究工作台权限' }),
  ).toBeVisible()

  await page.goto('/patient/invite')
  await expect(page.getByRole('heading', { name: '使用邀请码进入会话' })).toBeVisible()
  await expect(page.getByText('Q1 · 声音性别感')).not.toBeVisible()
  await expect(page.getByText('患者账户登录')).not.toBeVisible()
})

test('approved demo doctor can enter the isolated workspace', async ({ page }) => {
  await loginDoctor(page)
  await expect(page.getByText('这里仅显示由当前账户创建和负责的去标识化病例。')).toBeVisible()
  await expect(page.getByText('开发进度', { exact: true })).toBeVisible()
  await expect(page.getByText('当前安全门禁', { exact: true })).toBeVisible()
})

test('protected staff pages reject missing role credentials', async ({ page }) => {
  await page.goto('/doctor/workspace')
  await expect(page).toHaveURL(/\/doctor\/login$/)

  await page.goto('/admin/dashboard')
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('doctor interview exposes one guided question at a time', async ({ page }) => {
  await loginDoctor(page)
  await page.locator('.case-id-cell--button').filter({ hasText: 'DEMO-VOICE-001' }).click()
  await expect(page.getByText('Avatar 生成与版本审核')).toBeVisible()
  await page.getByRole('button', { name: '录入 Q1–Q8' }).first().click()

  await expect(page.locator('.guided-question-card')).toBeVisible()
  await expect(page.getByRole('heading', { name: '这个声音让患者感到多有恶意？' })).toBeVisible()
  await expect(page.getByText('这个声音像男声、女声，还是不确定或混合？')).not.toBeVisible()
  await expect(page.getByText('所有内容仅由医生录入，患者页面不会显示题目、选项或答案。')).toBeVisible()
})

test('administrator sees aggregate operations only', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByLabel('管理员邮箱').fill('admin@example.com')
  await page.getByLabel('密码').fill('Avatar-admin-2026')
  await page.getByRole('button', { name: '进入管理后台' }).click()

  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.getByText('系统边界状态')).toBeVisible()
  await expect(page.getByText('管理权限与病例内容严格隔离')).toBeVisible()
  await expect(
    page.getByText(/系统不会向管理员返回研究编号、Q1–Q8、患者调整原文、Prompt 或 Avatar 图片/),
  ).toBeVisible()
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
