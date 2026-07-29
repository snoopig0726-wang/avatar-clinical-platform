import { expect, test } from '@playwright/test'

test('patient sees image generation and review progress without refreshing', async ({ page }) => {
  let stage: 'voice_interview' | 'image_generation' | 'image_review' = 'voice_interview'

  await page.addInitScript(() => {
    window.localStorage.setItem('avatar-language', 'zh-CN')
    window.sessionStorage.setItem(
      'avatar.patient_session.session-1',
      'patient-test-token',
    )
  })

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname

    if (path.endsWith('/sessions/session-1')) {
      await route.fulfill({
        json: {
          session_id: 'session-1',
          case_id: 'case-1',
          study_code: null,
          status: 'active',
          stage,
          assessment_mode: 'new_assessment',
          has_prior_assessment: false,
          current_authorized_version_id: null,
          patient_satisfied_version_id: null,
          patient_satisfied_at: null,
          adjustments: { used: 0, limit: 3, has_pending: false },
          created_at: '2026-07-29T00:00:00Z',
          started_at: '2026-07-29T00:00:00Z',
          paused_at: null,
          ended_at: null,
          expires_at: '2026-07-30T00:00:00Z',
        },
      })
      return
    }

    if (path.endsWith('/patient-sessions/session-1/avatar')) {
      await route.fulfill({
        status: 409,
        json: {
          error: {
            code: 'STATE_CONFLICT',
            message: '尚未授权患者查看',
          },
        },
      })
      return
    }

    if (path.endsWith('/patient-sessions/session-1/adjustment-requests')) {
      await route.fulfill({
        json: {
          items: [],
          used: 0,
          limit: 3,
          has_pending: false,
        },
      })
      return
    }

    await route.fulfill({ status: 404, json: { detail: 'Unhandled test route' } })
  })

  await page.goto('/patient/session/session-1')
  await expect(
    page.getByRole('heading', { name: '请根据医生的提问，回答问题' }),
  ).toBeVisible()

  stage = 'image_generation'
  await expect(
    page.getByRole('heading', { name: '图片正在生成，请稍等' }),
  ).toBeVisible({ timeout: 7_000 })
  await expect(page.getByText('访谈已完成')).toBeVisible()
  await expect(page.getByText('生成并检查图片')).toBeVisible()
  await expect(page.getByText('医生确认后展示')).toBeVisible()
  await expect(page.getByText('正在生成并进行安全检查')).toBeVisible()

  stage = 'image_review'
  await expect(
    page.getByRole('heading', { name: '医生正在进行最后确认' }),
  ).toBeVisible({ timeout: 7_000 })
  await expect(page.getByText('医生正在审核图片')).toBeVisible()
})
