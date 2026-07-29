import { expect, test, type Page } from '@playwright/test'

const caseId = 'ui-flow-case'
const sessionId = 'ui-flow-session'
const imageDataUrl =
  'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='
const ageControlledInstruction =
  '适度增加人物年龄感，通过面部轮廓、发色与自然年龄特征呈现更年长的外观'
const gazeControlledInstruction =
  '根据患者描述调整眼睛颜色、大小、形状、眉形与凝视方向'

type FlowState = 'complete' | 'current' | 'pending' | 'skipped'

type Scenario = {
  name: string
  caseStatus: 'draft' | 'in_progress' | 'completed' | 'archived'
  sessionStatus?: 'active' | 'ended'
  newInviteIssued?: boolean
  visualConfirmed: boolean
  imageReviewed: boolean
  adjustmentStatus?: 'pending_doctor_review' | 'applied'
  expected: Record<string, FlowState>
}

const scenarios: Scenario[] = [
  {
    name: 'draft',
    caseStatus: 'draft',
    visualConfirmed: false,
    imageReviewed: false,
    expected: {
      'case-created': 'complete',
      'invite-redeemed': 'current',
      'session-started': 'pending',
      'visual-direction': 'pending',
      'image-generated': 'pending',
      'image-reviewed': 'pending',
      'patient-feedback': 'pending',
      'session-ended': 'pending',
      'case-archived': 'pending',
    },
  },
  {
    name: 'active-with-pending-feedback',
    caseStatus: 'in_progress',
    sessionStatus: 'active',
    visualConfirmed: true,
    imageReviewed: true,
    adjustmentStatus: 'pending_doctor_review',
    expected: {
      'case-created': 'complete',
      'invite-redeemed': 'complete',
      'session-started': 'complete',
      'visual-direction': 'complete',
      'image-generated': 'complete',
      'image-reviewed': 'complete',
      'patient-feedback': 'current',
      'session-ended': 'pending',
      'case-archived': 'pending',
    },
  },
  {
    name: 'completed-without-adjustment',
    caseStatus: 'completed',
    sessionStatus: 'ended',
    visualConfirmed: true,
    imageReviewed: true,
    expected: {
      'case-created': 'complete',
      'invite-redeemed': 'complete',
      'session-started': 'complete',
      'visual-direction': 'complete',
      'image-generated': 'complete',
      'image-reviewed': 'complete',
      'patient-feedback': 'skipped',
      'session-ended': 'complete',
      'case-archived': 'current',
    },
  },
  {
    name: 'new-invite-after-completed-session',
    caseStatus: 'in_progress',
    sessionStatus: 'ended',
    newInviteIssued: true,
    visualConfirmed: true,
    imageReviewed: true,
    adjustmentStatus: 'applied',
    expected: {
      'case-created': 'complete',
      'invite-redeemed': 'current',
      'session-started': 'pending',
      'visual-direction': 'pending',
      'image-generated': 'pending',
      'image-reviewed': 'pending',
      'patient-feedback': 'pending',
      'session-ended': 'pending',
      'case-archived': 'pending',
    },
  },
  {
    name: 'archived-after-feedback',
    caseStatus: 'archived',
    sessionStatus: 'ended',
    visualConfirmed: true,
    imageReviewed: true,
    adjustmentStatus: 'applied',
    expected: {
      'case-created': 'complete',
      'invite-redeemed': 'complete',
      'session-started': 'complete',
      'visual-direction': 'complete',
      'image-generated': 'complete',
      'image-reviewed': 'complete',
      'patient-feedback': 'complete',
      'session-ended': 'complete',
      'case-archived': 'complete',
    },
  },
]

function clinicalCase(scenario: Scenario) {
  const archived = scenario.caseStatus === 'archived'
  return {
    case_id: caseId,
    study_code: `FLOW-${scenario.name.toUpperCase()}`,
    status: scenario.caseStatus,
    created_at: '2026-07-27T09:00:00Z',
    updated_at: '2026-07-28T09:00:00Z',
    archived_at: archived ? '2026-07-28T09:00:00Z' : null,
    retention_due_at: archived ? '2026-08-27T09:00:00Z' : null,
    active_session_count: scenario.sessionStatus === 'active' ? 1 : 0,
    total_session_count: scenario.sessionStatus ? 1 : 0,
  }
}

function inviteList(scenario: Scenario) {
  if (!scenario.sessionStatus) return { items: [] }
  return {
    items: [
      ...(scenario.newInviteIssued
        ? [
            {
              invite_id: 'new-flow-invite',
              session_id: null,
              code: 'NEW-FLOW-CODE',
              code_mask: 'NEW-****',
              status: 'issued',
              created_at: '2026-07-28T10:00:00Z',
              expires_at: '2026-07-29T10:00:00Z',
            },
          ]
        : []),
      {
        invite_id: 'flow-invite',
        session_id: sessionId,
        code: null,
        code_mask: 'FLOW-****',
        status: scenario.sessionStatus,
        created_at: '2026-07-27T09:00:00Z',
        expires_at: '2026-07-29T09:00:00Z',
      },
    ],
  }
}

function patientSession(scenario: Scenario) {
  return {
    session_id: sessionId,
    case_id: caseId,
    study_code: null,
    status: scenario.sessionStatus,
    stage: 'avatar_review',
    assessment_mode: 'new_assessment',
    has_prior_assessment: false,
    adjustments: {
      used: scenario.adjustmentStatus ? 1 : 0,
      limit: 3,
      has_pending: scenario.adjustmentStatus === 'pending_doctor_review',
    },
    created_at: '2026-07-27T09:00:00Z',
    started_at: '2026-07-27T09:05:00Z',
    paused_at: null,
    ended_at:
      scenario.sessionStatus === 'ended' ? '2026-07-27T10:00:00Z' : null,
    expires_at: '2026-07-29T09:00:00Z',
  }
}

function adjustmentList(scenario: Scenario) {
  const hasAdjustment = Boolean(scenario.adjustmentStatus)
  return {
    items: hasAdjustment
      ? [
          {
            request_id: 'flow-adjustment',
            sequence_no: 1,
            instruction: 'Make the background slightly darker',
            status: scenario.adjustmentStatus,
            rejection_reason: null,
            submitted_at: '2026-07-27T09:30:00Z',
            reviewed_at:
              scenario.adjustmentStatus === 'applied'
                ? '2026-07-27T09:35:00Z'
                : null,
            controlled_instruction:
              scenario.adjustmentStatus === 'applied'
                ? ageControlledInstruction
                : null,
            suggested_controlled_instruction: ageControlledInstruction,
            controlled_options: [
              ageControlledInstruction,
              gazeControlledInstruction,
            ],
          },
        ]
      : [],
    used: hasAdjustment ? 1 : 0,
    limit: 3,
    has_pending: scenario.adjustmentStatus === 'pending_doctor_review',
    controlled_options: [ageControlledInstruction, gazeControlledInstruction],
  }
}

function versionList(scenario: Scenario) {
  if (!scenario.imageReviewed) return { items: [] }
  return {
    items: [
      {
        version_id: 'flow-version',
        case_id: caseId,
        generation_round: 1,
        generation_mode: 'initial',
        generation_status: 'approved',
        safety_status: 'passed',
        doctor_review_status: 'approved',
        provider_kind: 'mock',
        provider_model: 'mock-image',
        prompt_template_version: 'test',
        image_url: imageDataUrl,
        failure_code: null,
        is_current_candidate: true,
        is_authorized: scenario.caseStatus === 'in_progress',
        snapshot_available: true,
        doctor_reviewed_at: '2026-07-27T09:20:00Z',
        source_adjustment_request_id: null,
        created_at: '2026-07-27T09:15:00Z',
        completed_at: '2026-07-27T09:18:00Z',
      },
    ],
  }
}

function visualFeatures() {
  return {
    visual_feature_id: 'flow-visual',
    case_id: caseId,
    source_sound_description_id: 'flow-sound',
    system_result: {},
    doctor_edited: null,
    effective_features: {},
    controlled_options: {},
    mapping_explanation: {
      effective_power_level: 1,
      effective_malice_level: 0,
      safety_rules_applied: [],
      initial_risk_classification_performed: false,
    },
    mapping_version: 'test',
    is_doctor_confirmed: true,
    confirmed_at: '2026-07-27T09:12:00Z',
    updated_at: '2026-07-27T09:12:00Z',
  }
}

async function mockScenario(page: Page, scenario: Scenario) {
  await page.addInitScript(() => {
    window.localStorage.setItem('avatar-language', 'en')
    window.sessionStorage.setItem('avatar.staff_token', 'doctor-token')
  })

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown

    if (path === `/api/cases/${caseId}`) {
      body = clinicalCase(scenario)
    } else if (path === `/api/cases/${caseId}/session-invites`) {
      body = inviteList(scenario)
    } else if (path === `/api/sessions/${sessionId}`) {
      body = patientSession(scenario)
    } else if (path === `/api/cases/${caseId}/adjustment-requests`) {
      body = adjustmentList(scenario)
    } else if (path === `/api/cases/${caseId}/avatar-versions`) {
      body = versionList(scenario)
    } else if (path === `/api/cases/${caseId}/visual-features`) {
      if (!scenario.visualConfirmed) {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { code: 'STATE_CONFLICT', message: 'Not available' },
          }),
        })
        return
      }
      body = visualFeatures()
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

for (const scenario of scenarios) {
  test(`case workflow reflects ${scenario.name} data`, async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop')
    await mockScenario(page, scenario)
    await page.goto(`/doctor/cases/${caseId}`)

    const flow = page.locator('.case-flow-card')
    await expect(flow).toBeVisible()
    await expect(flow.locator('.case-flow-step')).toHaveCount(9)

    for (const [step, state] of Object.entries(scenario.expected)) {
      await expect(flow.locator(`[data-step="${step}"]`)).toHaveAttribute(
        'data-state',
        state,
      )
    }

    const dotBoxes = await flow.locator('.case-flow-dot').evaluateAll((dots) =>
      dots.map((dot) => {
        const box = dot.getBoundingClientRect()
        return { width: box.width, height: box.height }
      }),
    )
    expect(dotBoxes).toHaveLength(9)
    for (const box of dotBoxes) {
      expect(Math.abs(box.width - box.height)).toBeLessThan(0.5)
      expect(box.width).toBe(18)
    }

    await page.screenshot({
      path: `../tmp/ui-qa/case-flow-${scenario.name}.png`,
      fullPage: true,
    })
  })
}

test('expanded case workflow remains readable on mobile', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile')
  const scenario = scenarios[1]
  await mockScenario(page, scenario)
  await page.goto(`/doctor/cases/${caseId}`)

  const flow = page.locator('.case-flow-card')
  await expect(flow).toBeVisible()
  await expect(flow.locator('.case-flow-step')).toHaveCount(9)
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    )
    .toBe(true)

  await page.screenshot({
    path: '../tmp/ui-qa/case-flow-mobile.png',
    fullPage: true,
  })
})

test('controlled instructions follow the selected interface language', async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop')
  const scenario = scenarios[1]
  await mockScenario(page, scenario)
  await page.goto(`/doctor/cases/${caseId}`)

  await expect(
    page.getByText(
      'Moderately increase apparent age through facial contours, hair color, and natural age features',
    ),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Clinician adjustment' }).click()
  await expect(
    page.getByRole('radio', {
      name: 'Adjust eye color, size, shape, eyebrow shape, and gaze direction',
    }),
  ).toBeVisible()

  await page.getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: '简体中文' }).click()
  await page.getByRole('button', { name: '医生调整' }).click()
  await expect(
    page.getByRole('radio', { name: gazeControlledInstruction }),
  ).toBeVisible()
})
