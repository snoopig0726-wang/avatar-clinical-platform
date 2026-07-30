# 数据与隐私设计

- 文档版本：V1.2
- 当前状态：与 2026-07-30 代码实现同步
- 实现依据：`backend/app/models/entities.py`

## 1. 数据原则

- 患者不创建长期账户，只通过一次性邀请码进入受监督会话。
- 不保存患者姓名、身份证号、联系方式、住址或医院病历号。
- 医生只能访问自己创建的病例；患者只能访问当前设备绑定的会话。
- 管理员可管理员工账号、风险规则、聚合统计、脱敏审计和归档恢复，不可读取患者原始内容或图像。
- 邀请码、患者会话令牌和员工访问令牌只保存摘要。
- 患者调整原文、医生改写文本、受控指令和拒绝理由使用应用层加密字段。
- 审计日志不得记录调整原文、完整 Prompt、API Key、图像内容或邀请码明文。
- GPT Image 2 的 API Key 仅存在于服务端环境变量，不进入数据库、前端包或代码仓库。

## 2. 当前实体关系

| 表 | 用途 | 关键关系 |
|---|---|---|
| `users` | 医生和管理员账户 | 医生拥有多个病例 |
| `staff_access_sessions` | 员工登录会话 | 令牌只保存哈希，可撤销 |
| `email_verification_tokens` | 邮箱验证令牌 | 一次性使用并有过期时间 |
| `cases` | 去标识化病例 | 关联邀请、患者会话、特征和图像版本 |
| `session_invites` | 一次性邀请码 | 一个邀请码最多兑换一个患者会话 |
| `patient_sessions` | 受监督患者会话 | 绑定病例、邀请码、医生和设备 |
| `sound_descriptions` | 当前会话的 Q1–Q8 结构化答案 | `session_id` 唯一；每次新会话独立保存 |
| `visual_features` | 系统映射及医生确认后的视觉特征 | 引用声音描述；保留系统值、医生编辑值和生效值 |
| `avatar_versions` | 生图执行状态、结果和审核状态 | 直接承载生成生命周期；当前没有 `generation_jobs` 表 |
| `session_avatar_authorizations` | 患者可见版本授权 | 按会话授权或撤销具体图像版本 |
| `adjustment_requests` | 患者调整建议及医生处理 | 以 `(session_id, sequence_no)` 唯一 |
| `risk_rules` | 多语言风险规则 | 记录规则代码、触发词、上下文词、排除词和版本 |
| `retention_jobs` | 归档后的留存删除任务 | 使用不可逆病例摘要保留最小化任务记录 |
| `idempotency_records` | 写操作幂等 | 按调用者范围、操作和幂等键唯一 |
| `audit_logs` | 脱敏审计事件 | 只保存操作元数据 |

## 3. 核心表说明

### 3.1 `cases`

主要字段：

- `case_id`、`owner_doctor_id`、`study_code`
- `status`
- `archived_at`、`retention_started_at`、`retention_due_at`
- `created_at`、`updated_at`

`(owner_doctor_id, study_code)` 唯一。归档后开始 30 天留存计时。

### 3.2 `patient_sessions`

主要字段：

- `session_id`、`case_id`、`invite_id`、`supervising_doctor_id`
- `device_binding_hash`、`patient_session_token_hash`
- `status`、`assessment_mode`
- `consent_confirmed_by`、`consent_confirmed_at`、`consent_version`
- `patient_satisfied_version_id`、`patient_satisfied_at`
- `started_at`、`paused_at`、`ended_at`、`expires_at`、`last_seen_at`

同一病例可以依次创建多次会话。新邀请码兑换出的新会话拥有独立的 Q1–Q8、满意状态和调整额度。

### 3.3 `sound_descriptions`

当前字段为：

- `voice_gender`
- `age_sense`
- `pitch_level`
- `speaking_rate_level`
- `timbre`
- `emotions`
- `power_level`
- `malice_level`
- `answered_questions`

每个 `session_id` 最多一条声音描述。当前界面和后端允许最多 6 个受控情绪选项；文档中旧的“最多 3 个情绪”不再适用。

### 3.4 `visual_features`

主要字段：

- `source_sound_description_id`
- `system_result_json`
- `doctor_edited_json`
- `effective_json`
- `mapping_explanation`
- `mapping_version`
- `is_current`
- `confirmed_by`、`confirmed_at`

生图只使用医生确认后的 `effective_json`。创建新会话并重新录入 Q1–Q8 后，会生成与该声音描述关联的新视觉特征，不能沿用旧会话的“已生成”进度。

### 3.5 `avatar_versions`

生成状态直接保存在图像版本中，主要字段包括：

- 来源：`source_visual_feature_id`、`source_adjustment_request_id`
- 快照：`voice_features_snapshot_json`、`visual_features_snapshot_json`
- 生成：`generation_round`、`generation_mode`、`generation_status`
- Provider：`provider_kind`、`provider_model`、`provider_request_id`
- Prompt：`prompt_template_version`、`prompt_sha256`
- 输出：`image_object_key`、`output_mime_type`、`image_width`、`image_height`
- 安全：`safety_status`、语义安全 Provider/模型/请求 ID/分类
- 医生审核：`doctor_review_status`、审核人和审核时间
- 其他：`failure_code`、`is_current_candidate`、开始/完成时间

当前真实生图 Provider 为 OpenAI GPT Image 2。数据库只保存 Prompt 模板版本和摘要，不保存完整 Prompt。

### 3.6 `adjustment_requests`

主要字段：

- `case_id`、`session_id`、`sequence_no`
- `submitted_text_encrypted`
- `risk_status`、`risk_rule_version`
- `doctor_status`
- `clinician_edited_text_encrypted`
- `reviewed_instruction_encrypted`
- `rejection_reason_encrypted`
- 提交、审核、到期时间及审核人

业务约束：

- 每个患者会话最多提交 3 次调整建议。
- 新会话的额度从 0/3 重新开始，不与同一病例的历史会话累计。
- 患者原文先经过多语言风险检查。
- 医生可以直接接受系统研判，也可以选择性改写患者原话并重新映射为受控指令，或填写理由拒绝。
- 医生改写后的文本必须再次经过同一套风险规则。

### 3.7 `risk_rules`

主要字段：

- `rule_code`
- `category`
- `rule_type`
- `trigger_terms`
- `context_terms`
- `exclusion_terms`
- `patient_message_type`
- `version`
- `is_enabled`

当前规则版本为 `RISK-V1.3`。输入会先做 Unicode、大小写、空白、标点和简繁体等归一化，因此简体中文、繁体中文和英文输入都进入同一风险判定流程。刀具/锐器/创口与血液/伤害语义还会执行跨分隔符组合匹配。

### 3.8 `retention_jobs` 与 `audit_logs`

归档病例创建 30 天留存任务。到期删除病例、会话、答案、视觉特征、图像、调整文本和关联授权；任务记录只保留不可逆病例摘要、删除类别计数、尝试次数、状态和脱敏错误码。

审计日志只记录角色、资源 ID、操作、结果和白名单元数据，不记录任何敏感正文。

## 4. 生成与版本生命周期

1. 医生创建病例和邀请码。
2. 患者兑换邀请码，创建新的 `patient_sessions`。
3. 医生确认知情同意并启动会话。
4. 医生录入该会话的 Q1–Q8，写入 `sound_descriptions`。
5. 系统映射视觉特征，医生确认后写入 `visual_features`。
6. 医生发起生成，立即创建一条 `avatar_versions`，并在该记录上更新生成、安全和审核状态。
7. GPT Image 2 返回图像后，图像存储键及 Provider 元数据写回版本。
8. 安全检查通过且医生审核后，版本才可以授权患者查看。
9. 患者满意状态记录在当前 `patient_sessions`；调整请求也只计入当前会话。
10. 新邀请码创建新会话，所有会话级状态重新开始。

## 5. 已取消的旧设计

以下内容只存在于早期设计稿，不代表当前数据库：

- 独立 `generation_jobs` 表；
- `adjustment_requests.generation_id` 外键；
- 按病例生命周期累计 3 次调整；
- 每次成功后才创建图像版本；
- 最多 3 个情绪选项。

当前实现以 `avatar_versions` 作为生成状态和结果的统一持久化记录。
