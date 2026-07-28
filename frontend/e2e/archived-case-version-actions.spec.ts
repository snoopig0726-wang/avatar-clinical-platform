import { expect, test, type Page } from '@playwright/test'

const caseId = 'ui-archive-case'
const imageDataUrl =
  'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='

function caseResponse(status: 'in_progress' | 'archived') {
  return {
    case_id: caseId,
    study_code: status === 'archived' ? 'ARCHIVED-CASE' : 'ACTIVE-CASE',
    status,
    created_at: '2026-07-27T09:00:00Z',
    updated_at: '2026-07-28T09:00:00Z',
    archived_at: status === 'archived' ? '2026-07-28T09:00:00Z' : null,
    retention_due_at: status === 'archived' ? '2026-08-27T09:00:00Z' : null,
    active_session_count: 0,
    total_session_count: 1,
  }
}

function versionResponse(status: 'in_progress' | 'archived') {
  return {
    items: [3, 2, 1].map((round) => ({
      version_id: `version-${round}`,
      case_id: caseId,
      generation_round: round,
      generation_mode: round === 1 ? 'initial' : 'same_features_regenerate',
      generation_status: 'approved',
      safety_status: 'passed',
      doctor_review_status: 'approved',
      provider_kind: 'mock',
      provider_model: 'mock-image',
      prompt_template_version: 'test',
      image_url: imageDataUrl,
      failure_code: null,
      is_current_candidate: round === 2,
      is_authorized: status === 'in_progress' && round === 3,
      snapshot_available: true,
      doctor_reviewed_at: '2026-07-28T09:00:00Z',
      source_adjustment_request_id: null,
      created_at: '2026-07-28T08:00:00Z',
      completed_at: '2026-07-28T08:01:00Z',
    })),
  }
}

async function mockCaseApi(
  page: Page,
  status: 'in_progress' | 'archived',
) {
  await page.addInitScript(() => {
    window.localStorage.setItem('avatar-language', 'en')
    window.sessionStorage.setItem('avatar.staff_token', 'doctor-token')
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown

    if (path === `/api/cases/${caseId}`) {
      body = caseResponse(status)
    } else if (path === `/api/cases/${caseId}/session-invites`) {
      body = { items: [] }
    } else if (path === `/api/cases/${caseId}/adjustment-requests`) {
      body = {
        items: [],
        used: 0,
        limit: 3,
        has_pending: false,
        controlled_options: [],
      }
    } else if (path === `/api/cases/${caseId}/avatar-versions`) {
      body = versionResponse(status)
    } else if (path === `/api/cases/${caseId}/visual-features`) {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'STATE_CONFLICT', message: 'Not available' },
        }),
      })
      return
    } else if (
      path === '/api/cases/safety-events/recent'
      && url.searchParams.get('case_id') === caseId
    ) {
      body = { items: [] }
    } else {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'NOT_FOUND', message: path },
        }),
      })
      return
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

test('archived case versions only show download and delete actions', async ({
  page,
}, testInfo) => {
  await mockCaseApi(page, 'archived')
  await page.goto(`/doctor/cases/${caseId}`)

  const versions = page.locator('.avatar-version-grid')
  await expect(versions).toBeVisible()
  await expect(versions.getByRole('button', { name: 'Download version' })).toHaveCount(3)
  await expect(versions.getByRole('button', { name: 'Delete image' })).toHaveCount(3)
  await expect(versions.locator('button')).toHaveCount(6)

  await expect(
    versions.getByRole('button', { name: 'Authorize patient access' }),
  ).toHaveCount(0)
  await expect(
    versions.getByRole('button', { name: 'Select for rollback' }),
  ).toHaveCount(0)
  await expect(
    versions.getByRole('button', { name: 'Revoke patient access' }),
  ).toHaveCount(0)

  await page.screenshot({
    path: `../tmp/ui-qa/archived-case-actions-${testInfo.project.name}.png`,
    fullPage: true,
  })
})

test('active case version actions remain unchanged', async ({ page }) => {
  await mockCaseApi(page, 'in_progress')
  await page.goto(`/doctor/cases/${caseId}`)

  const versions = page.locator('.avatar-version-grid')
  await expect(versions).toBeVisible()
  await expect(
    versions.getByRole('button', { name: 'Revoke patient access' }),
  ).toHaveCount(1)
  await expect(
    versions.getByRole('button', { name: 'Authorize patient access' }),
  ).toHaveCount(1)
  await expect(
    versions.getByRole('button', { name: 'Select for rollback' }),
  ).toHaveCount(1)
  await expect(versions.getByRole('button', { name: 'Download version' })).toHaveCount(3)
  await expect(versions.getByRole('button', { name: 'Delete image' })).toHaveCount(2)
  await expect(
    versions.getByRole('button', {
      name: 'Visible to patient — cannot delete',
    }),
  ).toHaveCount(1)
})
