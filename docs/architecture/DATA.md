# 数据与隐私设计

- 所属产品：幻听患者个性化 Avatar 生成系统
- 关联 PRD：https://ycnhe29l1vtr.feishu.cn/docx/JAY0d7gkgoVAAjxa8vVcoQK1nKc
- 文档版本：V1.0
- 文档状态：Draft
- 来源：PRD V3.0 审查修订

## 1. 数据原则与通用约定

V1 不创建患者账户，不保存患者姓名、身份证号、联系方式、住址或医院病历号。患者只通过一次性邀请码和设备绑定的受监督会话访问数据。

- 数据库使用 PostgreSQL；主键统一使用 UUID，时间字段使用带时区的 `TIMESTAMPTZ`。
- 业务数据按病例隔离；医生只能访问自己创建或被明确授权的病例。
- 管理员只能访问账户、风险规则、聚合统计、脱敏审计和归档恢复操作，不能访问病例原文、访谈答案、患者调整原文或 Avatar 图片。
- 患者只能访问当前会话、当前已授权版本和自己的提交状态。
- 患者调整原文、邀请码展示密文、会话凭证等敏感字段使用应用层加密；密钥由独立 KMS 管理。
- 普通日志和审计日志不保存患者调整原文、Prompt、模型参数、图片内容或邀请码明文。
- 模型字段保持供应商无关，不把具体模型名称写死为业务枚举。

## 2. 实体关系总览

| 实体 | 作用 | 关系 |
|-|-|-|
| `users` | 医生和管理员账户 | 医生拥有多个 `cases`；管理员维护 `risk_rules` |
| `cases` | 去标识化病例 | 关联访谈、会话、版本、调整、任务和留存任务 |
| `session_invites` | 一次性邀请码 | 一个邀请码只绑定一个病例和一个患者会话 |
| `patient_sessions` | 受监督患者会话 | 绑定当前设备和会话凭证 |
| `sound_descriptions` | Q1–Q8 结构化答案快照 | 归属病例和会话，可被 Avatar 版本快照引用 |
| `visual_features` | 系统提取、医生确认的视觉特征 | 归属病例，可被 Avatar 版本快照引用 |
| `avatar_versions` | 每次成功生成的 Avatar 版本 | 通过父版本形成版本链 |
| `session_avatar_authorizations` | 当前会话的患者展示授权 | 关联会话和版本，支持授权、撤销和重新授权 |
| `adjustment_requests` | 患者调整建议 | 按病例累计最多 3 条，单条串行处理 |
| `generation_jobs` | 特征提取、生图和安全检查任务 | 关联病例、会话、版本和调整请求 |
| `risk_rules` | 管理员维护的风险规则 | 修改立即作用于新请求 |
| `audit_logs` | 脱敏审计事件 | 记录操作元数据，不记录原文或图片 |
| `retention_jobs` | 30 天到期删除任务 | 每个病例一个留存任务，支持重试 |

## 3. 表结构与约束

### 3.1 `users`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `user_id` | UUID | 是 | PK |
| `email` | VARCHAR(255) | 是 | UNIQUE；仅工作人员账户 |
| `password_hash` | VARCHAR(255) | 是 | 不保存明文密码 |
| `display_name` | VARCHAR(100) | 否 | 工作人员显示名称 |
| `role` | ENUM | 是 | `doctor` / `admin` |
| `email_verified` | BOOLEAN | 是 | 默认 `false` |
| `approval_status` | ENUM | 是 | `pending` / `approved` / `rejected` |
| `is_active` | BOOLEAN | 是 | 停用后不能登录 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `last_login_at` | TIMESTAMPTZ | 否 | 最近登录时间 |

索引：`UNIQUE(email)`、`(role, approval_status, is_active)`。

### 3.2 `cases`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `case_id` | UUID | 是 | PK |
| `owner_doctor_id` | UUID | 是 | FK → `users.user_id`，必须为 doctor |
| `study_code` | VARCHAR(100) | 是 | 去标识化研究编号；按医生范围可唯一 |
| `status` | ENUM | 是 | `draft` / `in_progress` / `completed` / `archived` |
| `current_version_id` | UUID | 否 | FK → `avatar_versions.version_id`，当前候选版本 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |
| `archived_at` | TIMESTAMPTZ | 否 | 归档时间 |
| `retention_started_at` | TIMESTAMPTZ | 否 | 等于病例归档时间 |
| `retention_due_at` | TIMESTAMPTZ | 否 | `retention_started_at + 30 days` |

约束：`status = archived` 时必须有 `archived_at`、`retention_started_at` 和 `retention_due_at`；V1 不使用 `deleted` 状态。索引：`(owner_doctor_id, status, updated_at DESC)`、`(retention_due_at)`、`(study_code)`。

### 3.3 `session_invites`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `invite_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `issuing_doctor_id` | UUID | 是 | FK → `users.user_id` |
| `code_hash` | BYTEA | 是 | 只用于校验，不保存明文 |
| `code_display_ciphertext` | BYTEA | 否 | 医生复制/查看时的加密展示值 |
| `code_mask` | VARCHAR(32) | 否 | 脱敏展示片段 |
| `status` | ENUM | 是 | `issued` / `redeemed_waiting` / `active` / `ended` / `revoked` / `expired` |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `expires_at` | TIMESTAMPTZ | 是 | 默认创建后 24 小时 |
| `redeemed_at` | TIMESTAMPTZ | 否 | 首次兑换时间 |
| `revoked_at` | TIMESTAMPTZ | 否 | 撤销时间 |
| `session_id` | UUID | 否 | FK → `patient_sessions.session_id`；兑换后写入 |

约束：一个邀请码最多兑换一次；`code_hash` UNIQUE；撤销、过期、已兑换或会话结束后不得再次兑换。索引：`UNIQUE(code_hash)`、`(case_id, status)`、`(expires_at)`。

### 3.4 `patient_sessions`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `session_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `invite_id` | UUID | 是 | FK → `session_invites.invite_id`；UNIQUE |
| `supervising_doctor_id` | UUID | 是 | FK → `users.user_id` |
| `device_binding_hash` | BYTEA | 是 | 当前设备绑定摘要，不保存设备原始标识 |
| `patient_session_token_hash` | BYTEA | 是 | 会话凭证摘要，不放入 URL |
| `status` | ENUM | 是 | `waiting_doctor` / `active` / `paused` / `ended` / `expired` |
| `started_at` | TIMESTAMPTZ | 否 | 医生启动时间 |
| `paused_at` | TIMESTAMPTZ | 否 | 最近暂停时间 |
| `ended_at` | TIMESTAMPTZ | 否 | 结束时间 |
| `expires_at` | TIMESTAMPTZ | 是 | 会话有效期 |
| `last_seen_at` | TIMESTAMPTZ | 否 | 最近心跳时间 |

约束：同一邀请码只能有一个会话；同一会话只允许绑定一个设备；安全暂停只能由医生恢复；会话结束后所有患者凭证立即失效。索引：`UNIQUE(invite_id)`、`(case_id, status)`、`(patient_session_token_hash)`。

### 3.5 `sound_descriptions`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `sound_description_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `session_id` | UUID | 是 | FK → `patient_sessions.session_id` |
| `voice_gender` | ENUM | 是 | `male` / `female` / `uncertain_mixed` |
| `age_group` | ENUM | 是 | `child` / `adolescent` / `young` / `middle` / `older` / `uncertain` |
| `pitch_level` | SMALLINT | 是 | 1–5 |
| `speech_rate` | SMALLINT | 否 | 1–5；未填写为 NULL |
| `voice_quality` | ENUM | 否 | 当前表单固定音色/口音选项 |
| `emotions` | JSONB | 是 | 六种固定情绪，多选，最多 3 项 |
| `power_level` | SMALLINT | 否 | 1–5；未填写为 NULL |
| `malice_level` | SMALLINT | 否 | 1–5；未填写为 NULL |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

约束：所有滑块只能为整数 1–5；`emotions` 只能来自 V1 固定枚举；不保存患者自由文本、额外情绪或身份信息。索引：`(case_id, updated_at DESC)`、`(session_id)`。

### 3.6 `visual_features`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `visual_feature_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `source_sound_description_id` | UUID | 是 | FK → `sound_descriptions.sound_description_id` |
| `system_result_json` | JSONB | 是 | 系统提取结果 |
| `doctor_edited_json` | JSONB | 否 | 医生修改后的结果 |
| `effective_json` | JSONB | 是 | 当前生图使用的视觉特征 |
| `mapping_explanation` | TEXT | 否 | 面向医生的结构化说明，不展示给患者 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间 |

V1 每次生成将 `effective_json` 快照写入 `avatar_versions.visual_snapshot`，不得依赖后续修改后的当前值重建历史版本。

### 3.7 `avatar_versions`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `version_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `parent_version_id` | UUID | 否 | 自引用 FK；首轮为空 |
| `source_adjustment_request_id` | UUID | 否 | FK → `adjustment_requests.request_id` |
| `generation_round` | SMALLINT | 是 | 首轮为 1，后续递增 |
| `image_object_key` | VARCHAR(512) | 是 | 对象存储键，不保存公开 URL |
| `mime_type` | VARCHAR(64) | 是 | V1 为 `image/png` |
| `width` | INT | 是 | V1 默认 1024 |
| `height` | INT | 是 | V1 默认 1024 |
| `sound_snapshot` | JSONB | 是 | Q1–Q8 快照 |
| `visual_snapshot` | JSONB | 是 | 生图时有效视觉特征快照 |
| `safety_status` | ENUM | 是 | `pending` / `passed` / `failed` |
| `doctor_review_status` | ENUM | 是 | `pending` / `approved` / `rejected` |
| `reviewed_by` | UUID | 否 | FK → `users.user_id` |
| `reviewed_at` | TIMESTAMPTZ | 否 | 医生审核时间 |
| `is_current_candidate` | BOOLEAN | 是 | 每个病例最多一个 true |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

只有 `safety_status = passed` 且 `doctor_review_status = approved` 的版本可以被授权。回退不删除其他版本，只切换 `is_current_candidate` 并撤销当前会话授权。索引：`(case_id, created_at DESC)`、`(case_id, is_current_candidate)`。

### 3.8 `session_avatar_authorizations`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `authorization_id` | UUID | 是 | PK |
| `session_id` | UUID | 是 | FK → `patient_sessions.session_id` |
| `version_id` | UUID | 是 | FK → `avatar_versions.version_id` |
| `status` | ENUM | 是 | `authorized` / `revoked` |
| `authorized_by` | UUID | 是 | FK → `users.user_id` |
| `authorized_at` | TIMESTAMPTZ | 是 | 授权时间 |
| `revoked_at` | TIMESTAMPTZ | 否 | 撤销时间 |
| `revoke_reason` | VARCHAR(100) | 否 | 回退、结束、归档或手动撤销 |

约束：一个会话同时最多一条 `authorized` 记录；授权版本必须安全检查通过且医生审核通过。索引：`(session_id, status)`、`(version_id)`。

### 3.9 `adjustment_requests`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `request_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `session_id` | UUID | 是 | FK → `patient_sessions.session_id` |
| `sequence_no` | SMALLINT | 是 | 1–3；UNIQUE(case_id, sequence_no) |
| `submitted_text_encrypted` | BYTEA | 否 | 风险通过后短期加密保存；风险失败为 NULL |
| `risk_status` | ENUM | 是 | `passed` / `blocked` / `timeout` |
| `doctor_status` | ENUM | 是 | `pending` / `approved_as_is` / `approved_edited` / `rejected` / `generating` / `applied` / `generation_failed` / `cancelled` |
| `reviewed_instruction_encrypted` | BYTEA | 否 | 医生批准后的受控指令 |
| `generation_id` | UUID | 否 | FK → `generation_jobs.generation_id` |
| `submitted_at` | TIMESTAMPTZ | 是 | 提交时间 |
| `reviewed_at` | TIMESTAMPTZ | 否 | 审核时间 |
| `reviewed_by` | UUID | 否 | FK → `users.user_id` |
| `expires_at` | TIMESTAMPTZ | 是 | 与病例留存周期一致 |

业务约束：每个病例最多 3 条风险通过的调整建议；同一病例同时最多 1 条 `pending`、`generating` 或待确认请求。风险校验失败不创建包含原文的调整记录，只写脱敏审计事件。索引：`(case_id, sequence_no)`、`(case_id, doctor_status)`。

### 3.10 `generation_jobs`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `generation_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id` |
| `session_id` | UUID | 否 | FK → `patient_sessions.session_id` |
| `version_id` | UUID | 否 | FK → `avatar_versions.version_id` |
| `adjustment_request_id` | UUID | 否 | FK → `adjustment_requests.request_id` |
| `generation_round` | SMALLINT | 是 | 1 或后续轮次 |
| `status` | ENUM | 是 | `extracting` / `generating` / `checking` / `pending_doctor_review` / `approved` / `rejected` / `failed` / `cancelled` |
| `idempotency_key` | VARCHAR(128) | 是 | UNIQUE(case_id, idempotency_key) |
| `model_provider` | VARCHAR(100) | 否 | 供应商无关记录 |
| `model_name` | VARCHAR(150) | 否 | 模型名称 |
| `model_version` | VARCHAR(150) | 否 | 模型版本 |
| `prompt_template_version` | VARCHAR(100) | 否 | Prompt 模板版本 |
| `safety_checker_version` | VARCHAR(100) | 否 | 安全检查版本 |
| `provider_request_id` | VARCHAR(255) | 否 | 供应商请求 ID |
| `requested_by` | UUID | 是 | FK → `users.user_id` |
| `started_at` | TIMESTAMPTZ | 否 | 开始时间 |
| `completed_at` | TIMESTAMPTZ | 否 | 完成时间 |
| `failed_at` | TIMESTAMPTZ | 否 | 失败时间 |
| `failure_code` | VARCHAR(100) | 否 | 脱敏失败类别 |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间 |

约束：所有写请求必须带幂等键；重复请求返回原任务。失败、取消、超时或安全检查失败不改变当前已授权版本。索引：`UNIQUE(case_id, idempotency_key)`、`(case_id, created_at DESC)`、`(status)`。

### 3.11 `risk_rules`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `rule_id` | UUID | 是 | PK |
| `category` | VARCHAR(100) | 是 | 风险类别 |
| `rule_type` | ENUM | 是 | `direct` / `context` / `crisis` / `pii` |
| `trigger_terms` | JSONB | 是 | 触发词或条件，按规则权限访问 |
| `exclusion_terms` | JSONB | 否 | 排除词或否定条件 |
| `risk_level` | ENUM | 是 | `sensitive` / `high_stimulus` / `crisis` |
| `action` | ENUM | 是 | `intercept` / `crisis_prompt` |
| `is_enabled` | BOOLEAN | 是 | 是否用于新请求 |
| `updated_by` | UUID | 是 | FK → `users.user_id`，必须为 admin |
| `updated_at` | TIMESTAMPTZ | 是 | 修改时间 |

管理员修改后立即用于新的风险校验，不追溯改变已完成请求。索引：`(is_enabled, rule_type)`。

### 3.12 `audit_logs`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `audit_id` | BIGSERIAL | 是 | PK |
| `actor_user_id` | UUID | 否 | FK → `users.user_id`；患者/系统事件为空 |
| `actor_type` | ENUM | 是 | `doctor` / `admin` / `patient` / `system` |
| `case_id` | UUID | 否 | FK → `cases.case_id` |
| `invite_id` | UUID | 否 | FK → `session_invites.invite_id` |
| `session_id` | UUID | 否 | FK → `patient_sessions.session_id` |
| `action` | VARCHAR(100) | 是 | 业务动作名称 |
| `result` | ENUM | 是 | `success` / `failed` / `blocked` |
| `metadata_json` | JSONB | 否 | 只允许脱敏元数据 |
| `created_at` | TIMESTAMPTZ | 是 | 事件时间 |

禁止写入：邀请码明文、患者调整原文、Prompt、模型参数、图片内容和风险命中原文。索引：`(case_id, created_at DESC)`、`(actor_user_id, created_at DESC)`、`(action, created_at DESC)`。

### 3.13 `retention_jobs`

| 字段 | 类型 | 必填 | 约束/说明 |
|-|-|-|-|
| `retention_job_id` | UUID | 是 | PK |
| `case_id` | UUID | 是 | FK → `cases.case_id`；UNIQUE |
| `retention_started_at` | TIMESTAMPTZ | 是 | 病例归档时间 |
| `retention_due_at` | TIMESTAMPTZ | 是 | 起算后 30 天 |
| `status` | ENUM | 是 | `scheduled` / `running` / `retrying` / `completed` / `failed` |
| `attempt_count` | INT | 是 | 默认 0 |
| `last_attempt_at` | TIMESTAMPTZ | 否 | 最近执行时间 |
| `deleted_categories_json` | JSONB | 否 | 各数据类别删除结果 |
| `last_error_code` | VARCHAR(100) | 否 | 脱敏错误类别 |
| `completed_at` | TIMESTAMPTZ | 否 | 删除完成时间 |

删除范围包括病例、会话、邀请码、Q1–Q8、视觉特征、全部 Avatar 版本、调整原文、风险处理数据、对象存储文件、备份和会话凭证。删除完成后只保留最小化删除任务结果，不保留可恢复业务数据。

## 4. 数据生命周期与访问

1. 病例创建后进入 `draft`，医生录入 Q1–Q8 和视觉特征。
2. 每次成功生成创建一条 `avatar_versions`；未通过安全检查、取消或失败的任务不创建可授权版本。
3. 医生审核通过并授权后，患者通过 `session_avatar_authorizations` 读取当前版本。
4. 医生回退时切换病例候选版本、撤销当前授权，并重新执行审核和授权。
5. 医生归档病例时立即结束患者会话并创建 `retention_jobs`；管理员恢复不暂停、不重置原删除时间。
6. 到期删除任务完成后，业务数据和备份不可恢复。

## 5. 下载数据边界

下载只包含指定已审核版本的 PNG 图片和该版本对应的 Q1–Q8 结构化答案。不得包含患者调整原文、风险命中原因、Prompt、模型参数、审计日志、未审核图片或其他版本。
