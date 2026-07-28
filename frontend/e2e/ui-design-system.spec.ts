import { expect, test, type Page } from '@playwright/test'

async function loginDoctor(page: Page) {
  await page.goto('/doctor/login')
  await page.getByLabel('机构邮箱').fill('doctor@example.com')
  await page.getByLabel('密码').fill('Avatar-demo-2026')
  await page.getByRole('button', { name: '进入工作台' }).click()
  await expect(page).toHaveURL(/\/doctor\/workspace$/, { timeout: 20_000 })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('avatar-language', 'zh-CN')
  })
})

test('patient and doctor surfaces follow the medical design tokens', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')

  await page.goto('/patient/invite')
  const patientPanel = page.locator('.access-page--patient .access-panel')
  const patientButton = page.getByRole('button', { name: '进入我的会话' })
  await expect(patientPanel).toBeVisible()
  await expect
    .poll(() =>
      patientPanel.evaluate((element) => {
        const style = getComputedStyle(element)
        return {
          background: style.backgroundColor,
          radius: style.borderRadius,
          font: style.fontFamily,
        }
      }),
    )
    .toEqual({
      background: 'rgb(252, 251, 247)',
      radius: '16px',
      font: expect.stringContaining('Noto Sans SC'),
    })
  await expect
    .poll(() =>
      patientButton.evaluate((element) => ({
        height: element.getBoundingClientRect().height,
        radius: getComputedStyle(element).borderRadius,
      })),
    )
    .toEqual({ height: 48, radius: '6px' })
  await page.screenshot({
    path: '../tmp/ui-qa/patient-invite-medical.png',
    fullPage: true,
  })

  await loginDoctor(page)
  const sidebar = page.locator('.workspace-sider')
  const statCard = page.locator('.stat-card').first()
  await expect(sidebar).toBeVisible()
  await expect
    .poll(() =>
      sidebar.evaluate((element) => getComputedStyle(element).backgroundColor),
    )
    .toBe('rgb(247, 244, 237)')
  await expect
    .poll(() =>
      statCard.evaluate((element) => {
        const style = getComputedStyle(element)
        return {
          background: style.backgroundColor,
          radius: style.borderRadius,
          shadow: style.boxShadow,
        }
      }),
    )
    .toEqual({
      background: 'rgb(247, 244, 237)',
      radius: '16px',
      shadow: 'none',
    })
  await page.screenshot({
    path: '../tmp/ui-qa/doctor-workspace-medical.png',
    fullPage: true,
  })
})

test('access-page image copy stays legible on every staff and patient entry', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')

  for (const [name, path] of [
    ['patient', '/patient/invite'],
    ['doctor', '/doctor/login'],
    ['admin', '/admin/login'],
  ] as const) {
    await page.goto(path)
    const eyebrow = page.locator('.access-aside .eyebrow--light')
    const supportingItems = page.locator('.access-aside__content li')
    const footnote = page.locator('.access-aside__foot')

    await expect(eyebrow).toBeVisible()
    await expect(eyebrow).toHaveCSS('color', 'rgb(247, 255, 252)')
    await expect(eyebrow).toHaveCSS('font-weight', '700')
    await expect(eyebrow).not.toHaveCSS('text-shadow', 'none')
    await expect(supportingItems.first()).toHaveCSS(
      'color',
      'rgba(255, 255, 255, 0.92)',
    )
    await expect(footnote).toHaveCSS('color', 'rgba(255, 255, 255, 0.8)')

    await page.screenshot({
      path: `../tmp/ui-qa/${name}-access-copy-contrast.png`,
      fullPage: true,
    })
  }
})

test('landing-page footer uses the same brand mark as the header', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  const headerMark = page.locator('.site-header .brand__mark')
  const footerMark = page.locator('.site-footer .brand__mark')

  await expect(headerMark).toBeVisible()
  await expect(footerMark).toBeVisible()

  const readMarkStyle = (element: HTMLElement) => {
    const style = getComputedStyle(element)
    const bar = element.querySelector('i')
    return {
      width: style.width,
      height: style.height,
      borderColor: style.borderColor,
      borderRadius: style.borderRadius,
      backgroundColor: style.backgroundColor,
      barColor: bar ? getComputedStyle(bar).backgroundColor : null,
    }
  }

  await expect
    .poll(async () => ({
      header: await headerMark.evaluate(readMarkStyle),
      footer: await footerMark.evaluate(readMarkStyle),
    }))
    .toEqual({
      header: await headerMark.evaluate(readMarkStyle),
      footer: await headerMark.evaluate(readMarkStyle),
    })

  await page.screenshot({
    path: `../tmp/ui-qa/landing-brand-unified-${testInfo.project.name}.png`,
    fullPage: true,
  })
})

test('Q1-Q8 enum choices are fully visible option cards', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')

  await loginDoctor(page)
  await page.getByLabel('搜索预约号').fill('DEMO-VOICE-001')
  await page.getByLabel('搜索预约号').press('Enter')
  const matchingCase = page
    .locator('.case-id-cell--button')
    .filter({ hasText: 'DEMO-VOICE-001' })
  await expect(matchingCase).toBeVisible()
  await matchingCase.click()
  const caseId = page.url().split('/').at(-1)!
  const sessionId = await page.evaluate(async (targetCaseId) => {
    const token = window.sessionStorage.getItem('avatar.staff_token')
    const response = await window.fetch(
      `/api/cases/${targetCaseId}/session-invites`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const payload = await response.json()
    return payload.items.find(
      (item: { session_id: string | null }) => item.session_id,
    )?.session_id
  }, caseId)

  expect(sessionId).toBeTruthy()
  await page.goto(`/doctor/cases/${caseId}/interview/${sessionId}`)
  const optionCards = page.locator('.guided-option-grid .ant-radio-wrapper')
  await expect(optionCards).toHaveCount(3, { timeout: 20_000 })
  await expect(page.locator('.guided-question .ant-select')).toHaveCount(0)
  await expect(optionCards.first()).toHaveCSS('min-height', '48px')
  await expect(optionCards.first()).toHaveCSS('border-radius', '10px')
  await page.screenshot({
    path: '../tmp/ui-qa/doctor-interview-options-medical.png',
    fullPage: true,
  })
})

test('active patient session uses the low-stimulation patient surface', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')

  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.patient_session.ui-patient', 'patient-token')
  })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/sessions/ui-patient') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'ui-patient',
          case_id: 'ui-case',
          study_code: null,
          status: 'active',
          stage: 'avatar_review',
          assessment_mode: 'new_assessment',
          has_prior_assessment: false,
          adjustments: { used: 0, limit: 3, has_pending: false },
          created_at: '2026-07-27T09:00:00Z',
          started_at: '2026-07-27T09:05:00Z',
          paused_at: null,
          ended_at: null,
          expires_at: '2026-07-28T09:00:00Z',
        }),
      })
      return
    }
    if (path === '/api/patient-sessions/ui-patient/avatar') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          version_id: 'ui-version',
          authorization_status: 'authorized',
          display_mode: 'mock_placeholder',
          image_url: null,
          message: null,
        }),
      })
      return
    }
    if (path === '/api/patient-sessions/ui-patient/adjustment-requests') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          items: [],
          used: 0,
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

  await page.goto('/patient/session/ui-patient')
  const patientStage = page.locator('.patient-avatar-stage')
  const adjustmentPanel = page.locator('.patient-adjustment-panel')
  await expect(patientStage).toBeVisible()
  await expect(adjustmentPanel).toBeVisible()
  await expect(patientStage).toHaveCSS('background-color', 'rgb(252, 251, 247)')
  await expect(patientStage).toHaveCSS('border-radius', '16px')
  await expect(page.getByRole('button', { name: '满意' })).toHaveCSS(
    'min-height',
    '48px',
  )
  await page.screenshot({
    path: '../tmp/ui-qa/patient-session-medical.png',
    fullPage: true,
  })
})

test('medical surfaces remain usable without horizontal overflow on mobile', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')

  for (const path of ['/patient/invite', '/doctor/login']) {
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
