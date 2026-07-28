import { expect, test } from '@playwright/test'

test('patient waiting state has a clear staggered pulse', async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.patient_session.test-waiting', 'test-token')
    window.localStorage.setItem('avatar-language', 'zh-CN')
  })
  await page.route('**/api/sessions/test-waiting', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: 'test-waiting',
        case_id: 'case-test',
        study_code: 'TEST',
        status: 'waiting_doctor',
        stage: 'waiting_doctor_start',
        assessment_mode: 'new_assessment',
        has_prior_assessment: false,
        adjustments: { used: 0, limit: 3, has_pending: false },
        created_at: '2026-07-28T00:00:00Z',
        started_at: null,
        paused_at: null,
        ended_at: null,
        expires_at: '2026-07-29T00:00:00Z',
      }),
    })
  })

  await page.goto('/patient/session/test-waiting')
  const rings = page.locator('.waiting-ring')
  await expect(rings).toHaveCount(3)
  await expect(rings.first()).toHaveCSS('animation-name', 'waiting-ripple')
  await expect(rings.nth(1)).toHaveCSS('animation-delay', '0.65s')
  await expect(rings.nth(2)).toHaveCSS('animation-delay', '1.3s')
  await expect(page.locator('.waiting-visual i')).toHaveCSS(
    'animation-name',
    'waiting-core',
  )
  await page.waitForTimeout(750)
  await page.screenshot({
    path: `../tmp/ui-qa/patient-waiting-pulse-${test.info().project.name}.png`,
    fullPage: true,
  })
})

test('patient sees a clear notice when the clinician ends the session', async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.patient_session.test-ended', 'test-token')
    window.localStorage.setItem('avatar-language', 'zh-CN')
  })
  let statusRequests = 0
  await page.route('**/api/sessions/test-ended', async (route) => {
    statusRequests += 1
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: 'test-ended',
        case_id: 'case-test',
        study_code: 'TEST',
        status: statusRequests === 1 ? 'waiting_doctor' : 'ended',
        stage: statusRequests === 1 ? 'waiting_doctor_start' : 'ended',
        assessment_mode: 'new_assessment',
        has_prior_assessment: false,
        adjustments: { used: 0, limit: 3, has_pending: false },
        created_at: '2026-07-27T00:00:00Z',
        started_at: '2026-07-27T00:01:00Z',
        paused_at: null,
        ended_at: '2026-07-27T00:02:00Z',
        expires_at: '2026-07-28T00:00:00Z',
      }),
    })
  })

  await page.goto('/patient/session/test-ended')

  await expect(page.getByRole('heading', { name: '医生正在为你准备' })).toBeVisible()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('会话已结束', { exact: true })).toBeVisible({
    timeout: 5_000,
  })
  await expect(
    dialog.getByText('会话已结束，感谢您的参与及配合！', { exact: true }),
  ).toBeVisible()
  await dialog.getByRole('button', { name: '知道了' }).click()
  await expect(page).toHaveURL('/patient/invite')
  await expect(dialog).toBeHidden()
  await expect
    .poll(() =>
      page.evaluate(() =>
        window.sessionStorage.getItem('avatar.patient_session.test-ended'),
      ),
    )
    .toBeNull()
})
