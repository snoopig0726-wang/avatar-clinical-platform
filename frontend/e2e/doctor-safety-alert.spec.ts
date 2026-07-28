import { expect, test } from '@playwright/test'

test('resolved discomfort disappears while a new sensitive adjustment stays visible', async ({
  page,
}) => {
  let sessionStatus: 'paused' | 'active' = 'paused'
  let safetyItems = [
    {
      event_id: 101,
      case_id: 'test-case',
      study_code: 'SAFETY-TEST',
      session_id: 'test-session',
      event_type: 'patient_discomfort',
      severity: 'critical',
      risk_rule_codes: [],
      created_at: '2026-07-27T10:00:00Z',
    },
  ]

  await page.addInitScript(() => {
    window.sessionStorage.setItem('avatar.staff_token', 'test-staff-token')
    window.localStorage.setItem('avatar-language', 'zh-CN')
  })
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown
    let status = 200

    if (path === '/api/cases/test-case') {
      body = {
        case_id: 'test-case',
        study_code: 'SAFETY-TEST',
        status: 'in_progress',
        created_at: '2026-07-27T09:00:00Z',
        updated_at: '2026-07-27T10:00:00Z',
        archived_at: null,
        retention_due_at: null,
        active_session_count: 1,
        total_session_count: 1,
      }
    } else if (path === '/api/cases/test-case/session-invites') {
      body = {
        items: [
          {
            invite_id: 'test-invite',
            session_id: 'test-session',
            code: null,
            code_mask: 'TEST-****',
            status: 'active',
            created_at: '2026-07-27T09:00:00Z',
            expires_at: '2026-07-28T09:00:00Z',
          },
        ],
      }
    } else if (path === '/api/sessions/test-session') {
      body = {
        session_id: 'test-session',
        case_id: 'test-case',
        study_code: 'SAFETY-TEST',
        status: sessionStatus,
        stage: sessionStatus,
        assessment_mode: 'new_assessment',
        has_prior_assessment: false,
        adjustments: { used: 0, limit: 3, has_pending: false },
        created_at: '2026-07-27T09:00:00Z',
        started_at: '2026-07-27T09:05:00Z',
        paused_at: sessionStatus === 'paused' ? '2026-07-27T10:00:00Z' : null,
        ended_at: null,
        expires_at: '2026-07-28T09:00:00Z',
      }
    } else if (path === '/api/cases/test-case/adjustment-requests') {
      body = {
        items: [],
        used: 0,
        limit: 3,
        has_pending: false,
        controlled_options: [],
      }
    } else if (path === '/api/cases/test-case/avatar-versions') {
      body = { items: [] }
    } else if (path === '/api/cases/test-case/visual-features') {
      status = 409
      body = { error: { code: 'STATE_CONFLICT', message: 'not ready' } }
    } else if (path === '/api/cases/safety-events/recent') {
      body = { items: safetyItems }
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

  await page.goto('/doctor/cases/test-case')
  const safetyAlert = page.locator('.case-safety-alert')
  await expect(safetyAlert).toContainText('患者表示不适，请立即关注')
  await expect(safetyAlert).toHaveClass(/ant-alert-error/)
  await expect(page.getByRole('button', { name: '医生恢复' })).toBeVisible()

  sessionStatus = 'active'
  safetyItems = []
  await expect(safetyAlert).toHaveCount(0, { timeout: 6_000 })
  await expect(page.getByRole('button', { name: '医生恢复' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '结束会话' })).toBeVisible()

  safetyItems = [
    {
      event_id: 102,
      case_id: 'test-case',
      study_code: 'SAFETY-TEST',
      session_id: 'test-session',
      event_type: 'sensitive_adjustment',
      severity: 'warning',
      risk_rule_codes: ['R-003'],
      created_at: '2026-07-27T10:05:00Z',
    },
  ]
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('系统拦截了一条包含敏感内容的患者调整建议', {
    timeout: 6_000,
  })
  await dialog.getByRole('button', { name: '知道了' }).click()
  await expect(safetyAlert).toContainText('系统拦截了患者提交的敏感调整建议')
  await expect(safetyAlert).toHaveClass(/ant-alert-warning/)
  await expect(safetyAlert).toContainText('敏感内容未进入生图流程')
})
