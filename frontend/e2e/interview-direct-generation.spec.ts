import { expect, test } from '@playwright/test'

const visualValues = {
  gender_expression: '男性基础表达',
  age_expression: '青年均衡比例',
  face_shape: '自然脸型轮廓',
  skin_texture: '柔和皮肤质感',
  facial_expression: '平淡表情',
  gaze: '正面自然平视',
  lighting: '低对比柔光',
  composition: '人物居中',
  background: '浅暖灰背景',
}

test('a new session can generate from its new visual features despite an older case image', async ({
  page,
}) => {
  let generationRequests = 0

  await page.addInitScript(() => {
    window.localStorage.setItem('avatar-language', 'zh-CN')
    window.sessionStorage.setItem('avatar.staff_token', 'doctor-test-token')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path.endsWith('/meta/voice-feature-contract')) {
      await route.fulfill({
        json: {
          question_order: [
            'voice_gender',
            'age_sense',
            'pitch_level',
            'speaking_rate_level',
            'timbre',
            'emotions',
            'power_level',
            'malice_level',
          ],
          enums: {
            voice_gender: ['male', 'female', 'uncertain_mixed'],
            age_sense: ['young'],
            timbre: ['clear_transparent'],
            emotions: ['indifference'],
          },
          optional_nullable_questions: [],
          emotion_max_length: 6,
          visual_feature_keys: Object.keys(visualValues),
          controlled_visual_options: {},
          initial_risk_classification: false,
        },
      })
      return
    }

    if (path.endsWith('/sessions/session-1/voice-features')) {
      await route.fulfill({
        json: {
          sound_description_id: 'sound-1',
          case_id: 'case-1',
          session_id: 'session-1',
          answers: { voice_gender: 'male' },
          answered_questions: ['voice_gender'],
          completed_count: 8,
          total_count: 8,
          complete: true,
          updated_at: '2026-07-29T00:00:00Z',
        },
      })
      return
    }

    if (path.endsWith('/cases/case-1/avatar-versions')) {
      await route.fulfill({
        json: {
          items: [{
            version_id: 'version-old',
            case_id: 'case-1',
            source_visual_feature_id: 'visual-old',
            generation_round: 1,
            generation_mode: 'initial',
            generation_status: 'approved',
            safety_status: 'passed',
            doctor_review_status: 'approved',
            provider_kind: 'openai',
            provider_model: 'gpt-image-2',
            prompt_template_version: 'test',
            image_url: '/old.png',
            failure_code: null,
            is_current_candidate: false,
            is_authorized: true,
            snapshot_available: true,
            doctor_reviewed_at: '2026-07-28T00:00:00Z',
            source_adjustment_request_id: null,
            created_at: '2026-07-28T00:00:00Z',
            completed_at: '2026-07-28T00:00:00Z',
          }],
        },
      })
      return
    }

    if (path.endsWith('/cases/case-1/visual-features')) {
      await route.fulfill({
        json: {
          visual_feature_id: 'visual-1',
          case_id: 'case-1',
          source_sound_description_id: 'sound-1',
          system_result: visualValues,
          doctor_edited: null,
          effective_features: visualValues,
          controlled_options: Object.fromEntries(
            Object.entries(visualValues).map(([key, value]) => [key, [value]]),
          ),
          mapping_explanation: {
            effective_power_level: 3,
            effective_malice_level: 2,
            safety_rules_applied: [],
            initial_risk_classification_performed: false,
          },
          mapping_version: 'test',
          is_doctor_confirmed: true,
          confirmed_at: '2026-07-29T00:00:00Z',
          updated_at: '2026-07-29T00:00:00Z',
        },
      })
      return
    }

    if (path.endsWith('/cases/case-1/avatar-generations') && request.method() === 'POST') {
      generationRequests += 1
      await route.fulfill({
        status: 202,
        json: {
          version_id: 'version-1',
          case_id: 'case-1',
          source_visual_feature_id: 'visual-1',
          generation_round: 1,
          generation_mode: 'initial',
          generation_status: 'queued',
          safety_status: 'pending',
          doctor_review_status: 'pending',
          provider_kind: 'openai',
          provider_model: 'gpt-image-2',
          prompt_template_version: 'test',
          image_url: null,
          failure_code: null,
          is_current_candidate: true,
          is_authorized: false,
          snapshot_available: true,
          doctor_reviewed_at: null,
          source_adjustment_request_id: null,
          created_at: '2026-07-29T00:00:00Z',
          completed_at: null,
        },
      })
      return
    }

    if (path.endsWith('/sessions/session-1')) {
      await route.fulfill({
        json: {
          session_id: 'session-1',
          case_id: 'case-1',
          study_code: null,
          status: 'active',
          stage: 'interview',
          assessment_mode: 'new_assessment',
          has_prior_assessment: true,
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

    if (path.endsWith('/cases/safety-events/recent')) {
      await route.fulfill({ json: { items: [] } })
      return
    }

    await route.fulfill({ status: 404, json: { detail: 'Unhandled test route' } })
  })

  await page.goto('/doctor/cases/case-1/interview/session-1')

  const generateButton = page.getByRole('button', { name: '直接生成图片' })
  await expect(generateButton).toBeVisible({ timeout: 20_000 })
  await generateButton.click()

  await expect(page.getByRole('button', { name: '查看图片进度' })).toBeVisible()
  await expect(page.getByText('图片生成任务已提交。可返回病例页面查看生成进度，完成后进行审核。')).toBeVisible()
  expect(generationRequests).toBe(1)
})
