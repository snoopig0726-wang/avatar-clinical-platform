import { expect, test } from '@playwright/test'

test('doctor sees a generated-image status and a transient satisfaction message', async ({
  page,
}) => {
  let satisfiedVersionId: string | null = null

  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.staff_token', 'test-staff-token')
    window.localStorage.setItem('avatar-language', 'en')
  })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown
    let status = 200

    if (path === '/api/cases/satisfaction-case') {
      body = {
        case_id: 'satisfaction-case',
        study_code: 'SATISFACTION-TEST',
        status: 'in_progress',
        created_at: '2026-07-28T09:00:00Z',
        updated_at: '2026-07-28T09:00:00Z',
        archived_at: null,
        retention_due_at: null,
        active_session_count: 1,
        total_session_count: 1,
      }
    } else if (path === '/api/cases/satisfaction-case/session-invites') {
      body = {
        items: [
          {
            invite_id: 'satisfaction-invite',
            session_id: 'satisfaction-session',
            code: null,
            code_mask: 'SAT-****',
            status: 'active',
            created_at: '2026-07-28T09:00:00Z',
            expires_at: '2026-07-29T09:00:00Z',
          },
        ],
      }
    } else if (path === '/api/sessions/satisfaction-session') {
      body = {
        session_id: 'satisfaction-session',
        case_id: 'satisfaction-case',
        study_code: 'SATISFACTION-TEST',
        status: 'active',
        stage: 'avatar_review',
        assessment_mode: 'reuse_previous',
        has_prior_assessment: true,
        current_authorized_version_id: 'version-1',
        patient_satisfied_version_id: satisfiedVersionId,
        patient_satisfied_at: satisfiedVersionId
          ? '2026-07-28T09:05:00Z'
          : null,
        adjustments: { used: 0, limit: 3, has_pending: false },
        created_at: '2026-07-28T09:00:00Z',
        started_at: '2026-07-28T09:01:00Z',
        paused_at: null,
        ended_at: null,
        expires_at: '2026-07-29T09:00:00Z',
      }
    } else if (path === '/api/cases/satisfaction-case/adjustment-requests') {
      body = {
        items: [],
        used: 0,
        limit: 3,
        has_pending: false,
        controlled_options: [],
      }
    } else if (path === '/api/cases/satisfaction-case/avatar-versions') {
      body = { items: [] }
    } else if (path === '/api/cases/satisfaction-case/visual-features') {
      status = 409
      body = { error: { code: 'STATE_CONFLICT', message: 'not ready' } }
    } else if (path === '/api/cases/safety-events/recent') {
      body = { items: [] }
    } else {
      status = 404
      body = { error: { code: 'NOT_FOUND', message: path } }
    }

    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })

  await page.goto('/doctor/cases/satisfaction-case')
  await expect(page.locator('.invite-list__item')).toBeVisible()
  const generatedStatus = page
    .locator('.invite-list__actions')
    .getByText('Image generated', { exact: true })
  await expect(generatedStatus).toHaveCount(0)

  satisfiedVersionId = 'version-1'

  const toast = page.getByText(
    'The patient is satisfied with the current image',
    { exact: true },
  )
  await expect(generatedStatus).toBeVisible({
    timeout: 6_000,
  })
  await expect(toast).toBeVisible()
  await expect(toast).toHaveCount(0, { timeout: 5_000 })
})

test('patient satisfaction is submitted to the session API', async ({ page }) => {
  let submittedFeedback: { version_id: string; satisfied: boolean } | null = null
  let satisfiedVersionId: string | null = null

  const sessionResponse = () => ({
    session_id: 'patient-satisfaction-session',
    case_id: 'patient-satisfaction-case',
    study_code: 'PATIENT-SATISFACTION',
    status: 'active',
    stage: 'avatar_review',
    assessment_mode: 'reuse_previous',
    has_prior_assessment: true,
    current_authorized_version_id: 'version-1',
    patient_satisfied_version_id: satisfiedVersionId,
    patient_satisfied_at: satisfiedVersionId
      ? '2026-07-28T09:05:00Z'
      : null,
    adjustments: { used: 0, limit: 3, has_pending: false },
    created_at: '2026-07-28T09:00:00Z',
    started_at: '2026-07-28T09:01:00Z',
    paused_at: null,
    ended_at: null,
    expires_at: '2026-07-29T09:00:00Z',
  })

  await page.addInitScript(() => {
    window.sessionStorage.setItem(
      'avatar.patient_session.patient-satisfaction-session',
      'test-patient-token',
    )
    window.localStorage.setItem('avatar-language', 'en')
  })
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let body: unknown
    let status = 200

    if (path === '/api/sessions/patient-satisfaction-session') {
      body = sessionResponse()
    } else if (
      path === '/api/patient-sessions/patient-satisfaction-session/avatar'
    ) {
      body = {
        version_id: 'version-1',
        display_mode: 'image',
        image_url:
          'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
      }
    } else if (
      path
      === '/api/patient-sessions/patient-satisfaction-session/adjustment-requests'
    ) {
      body = { items: [], used: 0, limit: 3, has_pending: false }
    } else if (
      path === '/api/patient-sessions/patient-satisfaction-session/avatar-feedback'
      && request.method() === 'POST'
    ) {
      submittedFeedback = request.postDataJSON() as {
        version_id: string
        satisfied: boolean
      }
      satisfiedVersionId = submittedFeedback.satisfied
        ? submittedFeedback.version_id
        : null
      body = sessionResponse()
    } else {
      status = 404
      body = { error: { code: 'NOT_FOUND', message: path } }
    }

    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })

  await page.goto('/patient/session/patient-satisfaction-session')
  await page.getByRole('button', { name: 'Satisfied' }).click()

  await expect(page.getByRole('heading', { name: 'Marked as satisfactory' }))
    .toBeVisible()
  expect(submittedFeedback).toEqual({
    version_id: 'version-1',
    satisfied: true,
  })
})
