import { expect, test, type Page } from '@playwright/test'

type LayoutIssue = {
  tag: string
  className: string
  text: string
  width: number
  height: number
  scrollWidth: number
  scrollHeight: number
  reason: 'clipped' | 'narrow-multiline'
}

async function setEnglish(page: Page) {
  await page.addInitScript(() => window.localStorage.setItem('avatar-language', 'en'))
}

async function captureLayout(page: Page, name: string) {
  await page.locator('.ant-spin-spinning').first().waitFor({ state: 'hidden' }).catch(() => {})
  await page.screenshot({
    path: `../tmp/english-layout-audit/verified-${name}.png`,
    fullPage: true,
  })

  const result = await page.evaluate(() => {
    const issues = Array.from(document.querySelectorAll<HTMLElement>('body *'))
      .filter((element) => {
        const text = element.innerText?.trim()
        if (!text || element.children.length > 0) return false
        const style = window.getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        return (
          style.display !== 'none' &&
          style.visibility !== 'hidden' &&
          rect.width > 0 &&
          rect.height > 0
        )
      })
      .flatMap((element): LayoutIssue[] => {
        const style = window.getComputedStyle(element)
        const rect = element.getBoundingClientRect()
        const text = element.innerText.trim().replace(/\s+/g, ' ')
        const lineHeight = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.2
        const lineCount = Math.max(1, Math.round(rect.height / lineHeight))
        const clipped =
          element.scrollWidth > element.clientWidth + 2 ||
          element.scrollHeight > element.clientHeight + 6
        const narrowMultiline =
          text.includes(' ') &&
          lineCount >= 3 &&
          rect.width < 170 &&
          text.length / lineCount < 18

        if (!clipped && !narrowMultiline) return []
        return [
          {
            tag: element.tagName.toLowerCase(),
            className: element.className?.toString().slice(0, 100) ?? '',
            text: text.slice(0, 160),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            scrollWidth: element.scrollWidth,
            scrollHeight: element.scrollHeight,
            reason: clipped ? 'clipped' : 'narrow-multiline',
          },
        ]
      })

    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      siderWidth:
        document.querySelector<HTMLElement>('.workspace-sider')?.getBoundingClientRect().width ??
        null,
      issues,
    }
  })

  console.log(`ENGLISH_LAYOUT:${name}:${JSON.stringify(result)}`)
  expect(result.documentWidth, `${name} has horizontal page overflow`).toBeLessThanOrEqual(
    result.viewportWidth + 1,
  )
  expect(
    result.issues.filter((issue) => issue.reason === 'clipped'),
    `${name} contains clipped English text`,
  ).toEqual([])
  return result
}

async function loginDoctor(page: Page) {
  await page.goto('/doctor/login')
  await page.getByLabel('Organization email').fill('doctor@example.com')
  await page.getByLabel('Password').fill('Avatar-demo-2026')
  await page.getByRole('button', { name: 'Enter workspace' }).click()
  await expect(page).toHaveURL(/\/doctor\/workspace$/, { timeout: 20_000 })
}

test('audit every English surface for clipping and awkward wrapping', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  await setEnglish(page)

  for (const [name, path] of [
    ['01-landing', '/'],
    ['02-patient-invite', '/patient/invite'],
    ['03-doctor-login', '/doctor/login'],
    ['04-doctor-application', '/doctor/apply'],
    ['05-admin-login', '/admin/login'],
    ['06-not-found', '/missing-page'],
  ] as const) {
    await page.goto(path)
    await captureLayout(page, name)
  }

  await loginDoctor(page)
  await expect(page.locator('.workspace-content')).toBeVisible()
  await expect(page.locator('.cases-card .ant-spin-spinning')).toHaveCount(0)
  await captureLayout(page, '07-doctor-workspace')

  await page.getByLabel('Search appointment ID').fill('DEMO-VOICE-001')
  await page.getByLabel('Search appointment ID').press('Enter')
  const matchingCase = page.locator('.case-id-cell--button').filter({ hasText: 'DEMO-VOICE-001' })
  await expect(matchingCase).toBeVisible()
  await matchingCase.click()
  await expect(page.getByRole('heading', { name: 'DEMO-VOICE-001' })).toBeVisible({
    timeout: 20_000,
  })
  await captureLayout(page, '08-doctor-case')

  const caseId = page.url().split('/').at(-1)!
  const sessionId = await page.evaluate(async (targetCaseId) => {
    const token = window.sessionStorage.getItem('avatar.staff_token')
    const response = await window.fetch(`/api/cases/${targetCaseId}/session-invites`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const payload = await response.json()
    return payload.items.find((item: { session_id: string | null }) => item.session_id)?.session_id
  }, caseId)
  expect(sessionId).toBeTruthy()
  await page.goto(`/doctor/cases/${caseId}/interview/${sessionId}`)
  await expect(page.locator('.guided-question-card')).toBeVisible({ timeout: 20_000 })
  await captureLayout(page, '09-doctor-interview')

  await page.goto('/admin/login')
  await page.getByLabel('Administrator email').fill('admin@example.com')
  await page.getByLabel('Password').fill('Avatar-admin-2026')
  await page.getByRole('button', { name: 'Enter administration' }).click()
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.locator('.admin-content')).toBeVisible()
  await captureLayout(page, '10-admin-dashboard')
})

test('audit active patient session in English', async ({ page }, testInfo) => {
  await setEnglish(page)
  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.patient_session.english-audit', 'patient-token')
  })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/sessions/english-audit') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'english-audit',
          case_id: 'english-case',
          study_code: null,
          status: 'active',
          stage: 'avatar_review',
          assessment_mode: 'new_assessment',
          has_prior_assessment: false,
          adjustments: { used: 1, limit: 3, has_pending: false },
          created_at: '2026-07-27T09:00:00Z',
          started_at: '2026-07-27T09:05:00Z',
          paused_at: null,
          ended_at: null,
          expires_at: '2026-07-28T09:00:00Z',
        }),
      })
      return
    }
    if (path === '/api/patient-sessions/english-audit/avatar') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          version_id: 'english-version',
          authorization_status: 'authorized',
          display_mode: 'mock_placeholder',
          image_url: null,
          message: null,
        }),
      })
      return
    }
    if (path === '/api/patient-sessions/english-audit/adjustment-requests') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          used: 1,
          limit: 3,
          has_pending: false,
        }),
      })
      return
    }
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'NOT_FOUND', message: path } }),
    })
  })

  await page.goto('/patient/session/english-audit')
  await expect(page.locator('.patient-avatar-stage')).toBeVisible()
  await captureLayout(page, `${testInfo.project.name}-11-patient-session`)
  await page.getByRole('button', { name: 'Adjust' }).click()
  await captureLayout(page, `${testInfo.project.name}-12-patient-adjustment`)
})

test('audit every English route on mobile', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')
  await setEnglish(page)

  for (const [name, path] of [
    ['01-landing', '/'],
    ['02-patient-invite', '/patient/invite'],
    ['03-doctor-login', '/doctor/login'],
    ['04-doctor-application', '/doctor/apply'],
    ['05-admin-login', '/admin/login'],
    ['06-not-found', '/missing-page'],
  ] as const) {
    await page.goto(path)
    await captureLayout(page, `mobile-${name}`)
  }

  await loginDoctor(page)
  await expect(page.locator('.workspace-content')).toBeVisible()
  await captureLayout(page, 'mobile-07-doctor-workspace')
  await page.getByLabel('Search appointment ID').fill('DEMO-VOICE-001')
  await page.getByLabel('Search appointment ID').press('Enter')
  const matchingCase = page.locator('.case-id-cell--button').filter({ hasText: 'DEMO-VOICE-001' })
  await expect(matchingCase).toBeVisible()
  await matchingCase.click()
  await expect(page.getByRole('heading', { name: 'DEMO-VOICE-001' })).toBeVisible({
    timeout: 20_000,
  })
  await captureLayout(page, 'mobile-08-doctor-case')

  const caseId = page.url().split('/').at(-1)!
  const sessionId = await page.evaluate(async (targetCaseId) => {
    const token = window.sessionStorage.getItem('avatar.staff_token')
    const response = await window.fetch(`/api/cases/${targetCaseId}/session-invites`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const payload = await response.json()
    return payload.items.find((item: { session_id: string | null }) => item.session_id)?.session_id
  }, caseId)
  expect(sessionId).toBeTruthy()
  await page.goto(`/doctor/cases/${caseId}/interview/${sessionId}`)
  await expect(page.locator('.guided-question-card')).toBeVisible({ timeout: 20_000 })
  await captureLayout(page, 'mobile-09-doctor-interview')

  await page.goto('/admin/login')
  await page.getByLabel('Administrator email').fill('admin@example.com')
  await page.getByLabel('Password').fill('Avatar-admin-2026')
  await page.getByRole('button', { name: 'Enter administration' }).click()
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.locator('.admin-content')).toBeVisible()
  await captureLayout(page, 'mobile-10-admin-dashboard')
})
