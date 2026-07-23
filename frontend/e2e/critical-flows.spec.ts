import { expect, test } from '@playwright/test'

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
})

test('approved demo doctor can enter the isolated workspace', async ({ page }) => {
  await page.goto('/doctor/login')
  await page.getByLabel('机构邮箱').fill('doctor@example.com')
  await page.getByLabel('密码').fill('Avatar-demo-2026')
  await page.getByRole('button', { name: '进入工作台' }).click()

  await expect(page).toHaveURL(/\/doctor\/workspace$/)
  await expect(page.getByText('受监督 Avatar 研究平台')).toBeVisible()
  await expect(page.getByText('这里仅显示由当前账户创建和负责的去标识化病例。')).toBeVisible()
})

test('administrator sees aggregate operations only', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByLabel('管理员邮箱').fill('admin@example.com')
  await page.getByLabel('密码').fill('Avatar-admin-2026')
  await page.getByRole('button', { name: '进入管理后台' }).click()

  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.getByText('独立管理后台')).toBeVisible()
  await expect(page.getByText('系统边界状态')).toBeVisible()
  await expect(page.getByText('管理员无法打开病例原文')).not.toBeVisible()
})
