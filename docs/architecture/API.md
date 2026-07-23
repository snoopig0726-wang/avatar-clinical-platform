# API 接口契约

- 所属产品：幻听患者个性化 Avatar 生成系统
- 关联 PRD：https://ycnhe29l1vtr.feishu.cn/docx/JAY0d7gkgoVAAjxa8vVcoQK1nKc
- 文档版本：V1.0
- 文档状态：Draft
- 来源：PRD V3.0 审查修订

## 1. 契约范围与统一约定

本文件定义目标 V1 医生—患者主链路及受限管理员后台的资源型 API。管理员接口只返回账户、规则、聚合统计、脱敏审计和归档恢复所需的最小字段。

### 1.1 基础约定

- Base URL：`/api`；V1 暂不在路径中增加版本号。
- 请求和响应默认使用 `application/json; charset=utf-8`。
- 时间使用 ISO 8601 UTC，例如 `2026-07-18T08:30:00Z`。
- 资源 ID 使用 UUID；分页使用 `page`、`page_size`，默认 `page_size=20`，最大 100。
- 所有响应都可通过 `X-Request-Id` 追踪；服务端没有收到该请求头时自行生成。
- 任务类接口返回 `job_id`，客户端通过轮询查询，不使用 WebSocket。
- 患者不注册、不登录、不持有长期账户，只使用一次性邀请码兑换当前设备会话。

### 1.2 认证与凭证

医生接口使用机构账户 JWT：

```http
Authorization: Bearer <doctor_access_token>
```

患者接口使用兑换后生成的短期会话凭证：

```http
X-Session-Token: <patient_session_token>
```

患者凭证只在请求头中传递，不放入 URL、日志、下载文件或前端分享链接。服务端只保存凭证哈希，并将凭证绑定到兑换设备。

### 1.3 幂等与并发

- 除登录、退出和读取接口外，所有写接口必须携带 `Idempotency-Key`。
- 幂等键在同一资源范围内至少保留 24 小时。
- 相同幂等键和相同请求体返回第一次结果；相同幂等键但请求体不同返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 状态转换使用数据库事务和前置状态校验；并发冲突返回 `409 STATE_CONFLICT`。
- 同一病例同时只能有一个生成任务进入 `generating/checking`，同一病例同时只能有一条待处理或生成中的患者调整。
- 登录、医生申请、邮箱验证、邀请码兑换和患者调整提交使用 Redis 窗口限流；键只包含服务端密钥生成的匿名摘要，不保存邮箱、邀请码、患者凭证或 IP 明文。
- 病例归档、特征确认、生成、审核、回退、授权、邀请码兑换和调整额度变更使用 PostgreSQL 行锁串行化同一病例的关键状态。

### 1.4 统一错误响应

```json
{
  "error": {
    "code": "SESSION_ENDED",
    "message": "会话已结束或无权访问",
    "request_id": "req_01J...",
    "details": {}
  }
}
```

错误码约定：

| HTTP | code | 说明 |
|-|-|-|
| 400 | `INVALID_REQUEST` | JSON、参数或 Header 格式错误 |
| 401 | `UNAUTHENTICATED` | 缺少或无效的工作人员凭证 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在或当前角色无权访问；不泄露资源存在性 |
| 409 | `STATE_CONFLICT` | 当前状态不允许该操作 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 幂等键与原请求体不一致 |
| 422 | `VALIDATION_ERROR` | 字段、枚举或 Q1–Q8 约束不符合 V1 |
| 422 | `RISK_BLOCKED` | 调整文本风险校验失败；不保存原文、不消耗次数 |
| 429 | `RATE_LIMITED` | 请求频率超过公开入口限制；响应包含 `Retry-After` |
| 503 | `DEPENDENCY_UNAVAILABLE` | 生产环境的请求保护或安全依赖不可用，失败关闭 |
| 429 | `RATE_LIMITED` | 超出接口或邀请码尝试频率 |
| 502 | `MODEL_PROVIDER_ERROR` | 外部模型供应商失败；不替换当前版本 |
| 503 | `DEPENDENCY_UNAVAILABLE` | 风险、安全检查、数据库或任务服务暂不可用 |

### 1.5 接口条目的通用字段

下文接口表中的每一行都继承以下请求/响应约定；接口有额外要求时在该行或小节中覆盖：

- 请求头：医生接口带 `Authorization: Bearer <doctor_access_token>`；患者接口带 `X-Session-Token: <patient_session_token>`；写接口再带 `Idempotency-Key`；JSON 请求带 `Content-Type: application/json`。
- 路径参数：花括号中的参数必须进行 UUID 格式校验；不属于当前医生病例或当前患者会话的资源统一返回 `404 RESOURCE_NOT_FOUND`。
- Query 参数：未特别说明的查询接口只接受分页参数 `page`、`page_size` 和表格列出的过滤条件；未知参数返回 `400 INVALID_REQUEST`。
- 请求 JSON：表格中的 Request 是必填/可选字段摘要；未列出的字段不得静默接收，返回 `400 INVALID_REQUEST`。
- 响应 JSON：成功响应至少包含资源 ID、状态和服务端时间戳；任务类响应必须包含 `job_id`、`status`，并可包含 `poll_after_ms`。
- 错误响应：所有失败均使用 1.4 的统一错误结构，并携带 `request_id`；权限不足与资源不存在均使用 404。
- 幂等结果：标记为“必须”的写接口缺少 `Idempotency-Key` 返回 `400 INVALID_REQUEST`；重复请求按 1.3 返回第一次成功或失败结果，不重复创建资源/任务。
- 患者可见性：除患者专用读取/写入接口外，医生接口响应不代表患者可见；患者只能通过当前会话接口读取已授权版本、调整处理状态和固定提示。

## 2. 状态、权限与可见性

### 2.1 状态转换

| 对象 | 状态 | 允许的主要转换 |
|-|-|-|
| case | `draft` / `in_progress` / `completed` / `archived` | `draft → in_progress → completed → archived`；归档不可直接恢复患者旧会话 |
| invite | `issued` / `redeemed_waiting` / `active` / `ended` / `revoked` / `expired` | `issued → redeemed_waiting → active → ended`；`issued → revoked/expired` |
| session | `waiting_doctor` / `active` / `paused` / `ended` / `expired` | `waiting_doctor → active → paused → active → ended`；结束后不可恢复 |
| generation job | `queued` / `extracting` / `generating` / `checking` / `pending_doctor_review` / `approved` / `rejected` / `failed` / `cancelled` | 只能按任务编排顺序前进；终态不可重新执行 |
| adjustment request | `pending` / `approved_as_is` / `approved_edited` / `rejected` / `generating` / `applied` / `generation_failed` / `cancelled` | `pending → approved_* / rejected`；批准后 `approved_* → generating → applied/generation_failed` |
| authorization | `authorized` / `revoked` | 授权后可撤销；回退、结束、归档自动撤销 |

### 2.2 角色边界

- 医生：访问有权处理的病例，启动/暂停恢复/结束会话，保存 Q1–Q8，生成、审核、回退、授权和下载。
- 患者：兑换邀请码，查询当前会话，查看已授权版本，提交最多 3 次调整，触发安全暂停；不能访问病例列表、历史版本、未审核图片或下载。
- 管理员：只能访问第 14 节定义的账户、规则、聚合统计、脱敏审计、归档恢复和删除任务状态接口。

## 3. 认证接口

### 3.1 医生账户申请与邮箱验证

```http
POST /api/auth/doctor-applications
POST /api/auth/verify-email
```

账户申请和邮箱验证均要求 `Idempotency-Key`。申请成功后仍不能登录；必须先完成机构邮箱验证，再由管理员审批。`local`/`test` 环境可在申请响应中返回一次性开发验证令牌，生产环境不得返回该令牌。

### 3.2 医生登录

```http
POST /api/auth/login
```

角色：医生/管理员。幂等：不需要。

请求：

```json
{"email":"doctor@example.com","password":"***"}
```

响应：

```json
{"access_token":"<jwt>","token_type":"Bearer","expires_at":"2026-07-19T08:30:00Z","user":{"user_id":"uuid","role":"doctor","display_name":"医生"}}
```

错误：`UNAUTHENTICATED`、账号未审批、账号已停用时均不泄露账户存在性。

### 3.3 退出和当前用户

```http
POST /api/auth/logout
GET  /api/users/me
```

`logout` 撤销当前 JWT/服务端会话；`users/me` 返回当前工作人员角色和权限范围。

## 4. 病例接口

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| GET | `/api/cases?page=1&page_size=20&status=draft` | 医生 | Query 分页/状态 | `items[]`、`page`、`page_size`、`total` | 401 | 不需要 |
| POST | `/api/cases` | 医生 | `{study_code}` | `case_id`、`status=draft`、时间 | 401、422 | 必须；重复返回同一病例 |
| GET | `/api/cases/{case_id}` | 医生 | — | 病例、当前候选版本、会话摘要 | 404 | 不需要 |
| PUT | `/api/cases/{case_id}` | 医生 | `{study_code,status?}` | 更新后的病例 | 404、409 | 必须 |
| POST | `/api/cases/{case_id}/archive` | 医生 | `{reason?}` | `status=archived`、`retention_due_at` | 404、409 | 必须；重复归档返回当前结果 |
| POST | `/api/admin/cases/{case_id}/restore` | 管理员 | `{reason?}` | 恢复后的病例状态 | 404、409 | 必须 |

归档立即结束所有关联患者会话并撤销授权。恢复病例不恢复旧患者会话；医生必须创建新邀请码。30 天到期后病例不可恢复。

创建病例示例：

```http
POST /api/cases
Authorization: Bearer <doctor_access_token>
Idempotency-Key: case-create-001
```

```json
{"study_code":"ST-2026-0001"}
```

```json
{"case_id":"case-uuid","study_code":"ST-2026-0001","status":"draft","created_at":"2026-07-18T08:30:00Z"}
```

## 5. 邀请码与会话接口

### 5.1 邀请码

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| POST | `/api/cases/{case_id}/session-invites` | 医生 | `{expires_in_hours?:24}` | `invite_id`、一次性 `code`、`status=issued`、`expires_at` | 404、409 archived | 必须 |
| GET | `/api/cases/{case_id}/session-invites` | 医生 | Query `status?` | 邀请码状态列表；不返回已失效明文 | 404 | 不需要 |
| DELETE | `/api/session-invites/{invite_id}` | 医生 | — | `status=revoked` | 404、409 redeemed/ended | 必须 |
| POST | `/api/session-invites/redeem` | 患者设备 | `{code,device_binding}` | `session_id`、`patient_session_token`、`status=waiting_doctor`、`expires_at` | 404、409、429 | 必须 |

兑换后邀请码状态变为 `redeemed_waiting`，同一邀请码不可再次兑换。换设备必须由医生创建新邀请码；同一设备刷新和短暂断网通过原会话凭证恢复。

兑换响应示例：

```json
{
  "session_id":"session-uuid",
  "patient_session_token":"<short-lived-token>",
  "status":"waiting_doctor",
  "expires_at":"2026-07-19T08:30:00Z"
}
```

### 5.2 会话状态与控制

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| GET | `/api/sessions/{session_id}` | 医生/患者 | — | 当前状态、阶段、当前授权版本摘要、调整次数、时间 | 404 | 不需要 |
| POST | `/api/sessions/{session_id}/start` | 医生 | `{}` | `status=active`、`started_at` | 404、409 waiting_doctor only | 必须 |
| POST | `/api/patient-sessions/{session_id}/pause` | 患者 | `{reason?}` | `status=paused`、`paused_at` | 404、409 active only | 必须 |
| POST | `/api/sessions/{session_id}/resume` | 医生 | `{}` | `status=active` | 404、409 paused only | 必须 |
| POST | `/api/sessions/{session_id}/stop` | 医生 | `{reason?}` | `status=ended`、`ended_at` | 404、409 not ended | 必须 |

安全暂停只停止患者访问和后续交互，不允许患者自行恢复。会话结束后旧设备、旧页面、旧链接和旧凭证全部失效。

状态响应示例：

```json
{
  "session_id":"session-uuid",
  "status":"active",
  "stage":"awaiting_authorization",
  "current_authorized_version_id":null,
  "adjustments":{"used":1,"limit":3,"has_pending":false},
  "expires_at":"2026-07-19T08:30:00Z"
}
```

## 6. Q1–Q8 和视觉特征接口

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| GET | `/api/cases/{case_id}/voice-features` | 医生 | — | 当前 Q1–Q8、保存时间和完成度 | 404 | 不需要 |
| PUT | `/api/sessions/{session_id}/voice-features/{question_key}` | 医生 | 题目对应结构化值 | 该题值、完成度 | 404、409 session not active、422 | 必须 |
| POST | `/api/cases/{case_id}/extract-features` | 医生 | `{session_id}` | `job_id`、`status=extracting` | 404、409 Q1–Q8 incomplete | 必须 |
| GET | `/api/cases/{case_id}/visual-features` | 医生 | — | 系统结果、医生修改结果、有效结果 | 404、409 not extracted | 不需要 |
| PUT | `/api/cases/{case_id}/visual-features` | 医生 | `{effective_features,restore_system_result?}` | 更新后的有效视觉特征 | 404、409 | 必须 |

`question_key` 只能是当前 V1 Q1–Q8 字段。接口不得接受患者姓名、联系方式、自由文本情绪或身份描述。

Q1–Q8 保存示例：

```json
{
  "value":"male",
  "source":"doctor_interview",
  "client_updated_at":"2026-07-18T08:35:00Z"
}
```

```json
{
  "question_key":"voice_gender",
  "value":"male",
  "completed":true,
  "updated_at":"2026-07-18T08:35:01Z"
}
```

## 7. 生成、任务和图片安全检查

### 7.1 创建和查询生成任务

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| POST | `/api/cases/{case_id}/generations` | 医生 | `{session_id,generation_round?,source_adjustment_request_id?}` | `job_id`、`status=queued` | 404、409 incomplete/concurrent | 必须 |
| GET | `/api/generation-jobs/{job_id}` | 医生 | — | 任务状态、版本 ID、脱敏失败码 | 404 | 不需要 |
| POST | `/api/generation-jobs/{job_id}/cancel` | 医生 | `{reason?}` | `status=cancelled` | 404、409 terminal | 必须 |
| GET | `/api/generation-jobs/{job_id}/safety-check` | 医生 | — | `safety_status`、`checker_version`、检查时间 | 404、409 not checked | 不需要 |

生成流程：`queued → extracting → generating → checking → pending_doctor_review`。安全检查失败、超时、取消或供应商拒绝不得改变当前已授权版本。

任务响应示例：

```json
{
  "job_id":"job-uuid",
  "status":"pending_doctor_review",
  "version_id":"version-uuid",
  "generation_round":1,
  "safety_status":"passed",
  "poll_after_ms":2000
}
```

模型供应商、模型名称、Prompt 和供应商请求 ID 不暴露给患者；供应商调用只在服务端适配器中完成。

## 8. 医生审核、版本和患者授权

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| GET | `/api/cases/{case_id}/avatar-versions` | 医生 | Query `page?` | 版本列表、审核状态、当前候选标识 | 404 | 不需要 |
| GET | `/api/cases/{case_id}/avatar-versions/{version_id}` | 医生 | — | 版本详情、Q1–Q8/视觉特征快照、审核状态 | 404 | 不需要 |
| POST | `/api/avatar-versions/{version_id}/review` | 医生 | `{decision:approve\|reject}` | 更新后的审核状态；不会自动授权 | 404、409 not pending review | 必须 |
| POST | `/api/avatar-versions/{version_id}/rollback` | 医生 | `{session_id?,reason?}` | 历史版本重新进入待审核并撤销病例现行授权 | 404、409 invalid version | 必须 |
| POST | `/api/avatar-versions/{version_id}/authorize` | 医生 | `{session_id}` | `authorization_id`、`status=authorized` | 404、409 not approved/current candidate/session invalid | 必须 |
| POST | `/api/cases/{case_id}/authorization/revoke` | 医生 | `{session_id,reason?}` | `status=revoked` | 404、409 no active auth | 必须 |
| GET | `/api/patient-sessions/{session_id}/avatar` | 患者 | — | 当前会话已授权版本和短时图片地址 | 404、409 paused/ended/not authorized | 不需要 |

安全检查通过不代表医生审核通过。只有安全检查通过、医生审核通过、版本为病例当前候选版本且当前会话已授权时，患者接口才返回图片。

回退是事务操作：切换病例当前候选版本，撤销该病例所有当前患者会话授权，并要求医生重新审核和授权。回退不会删除其他版本。

患者 Avatar 响应示例：

```json
{
  "session_id":"session-uuid",
  "version_id":"version-uuid",
  "image":{"url":"<short-lived-url>","mime_type":"image/png","expires_at":"2026-07-18T08:40:00Z"},
  "notice":"这是对声音描述的非诊断、非真实身份复刻的视觉表达",
  "doctor_reviewed":true
}
```

患者接口不得返回未审核图片、历史版本、Prompt、模型参数或风险命中原文。

## 9. 患者调整建议接口

| Method | Path | Role | Request | Response | Errors / 前置状态 | 幂等 |
|-|-|-|-|-|-|-|
| POST | `/api/patient-sessions/{session_id}/adjustment-requests` | 患者 | `{instruction}` | `request_id`、`status=pending`、`used_count` | 404、409 not authorized/has pending/limit reached、422 risk blocked | 必须 |
| GET | `/api/cases/{case_id}/adjustment-requests` | 医生 | Query `status?` | 调整列表；原文仅当前监督医生可见 | 404 | 不需要 |
| GET | `/api/adjustment-requests/{request_id}` | 医生/患者 | — | 状态、时间、患者可见结果 | 404 | 不需要 |
| POST | `/api/adjustment-requests/{request_id}/review` | 医生 | `{decision:approve_as_is\|approve_edited\|reject,controlled_instruction?}` | 审核状态 | 404、409 not pending、422 | 必须 |
| POST | `/api/adjustment-requests/{request_id}/generate` | 医生 | `{}` | `job_id`、`status=queued` | 404、409 not approved/concurrent | 必须 |

业务规则：

- 每个病例最多 3 条风险校验通过并创建的调整请求；风险失败不创建记录、不保存原文、不发送模型、不消耗次数。
- 同一病例同时最多 1 条 `pending`、`generating` 或待确认调整请求。
- 医生拒绝、生成失败、取消不会创建新 Avatar 版本；已创建的调整序号不回收。
- 患者只能看到 `pending`、`applied`、`rejected` 或 `generation_failed` 等结果状态，不看到内部风险原因、Prompt 或医生编辑指令。

患者提交示例：

```json
{"instruction":"希望表情更平静，减少阴影和紧张感"}
```

```json
{
  "request_id":"adjustment-uuid",
  "status":"pending",
  "used_count":1,
  "limit":3,
  "patient_message":"已提交给医生审核"
}
```

## 10. 下载接口

```http
GET /api/cases/{case_id}/avatar-versions/{version_id}/download
```

角色：医生。必须拥有病例权限，且版本已通过安全检查和医生审核。响应为下载流：

- `Content-Type: application/zip`；
- `Content-Disposition: attachment; filename="avatar-{version_id}.zip"`；
- 包含 `avatar.png` 和 `voice-features.json`；
- `voice-features.json` 只包含该版本对应的 Q1–Q8 结构化答案。

不得包含患者调整原文、风险命中原因、Prompt、模型参数、审计日志、未审核图片或其他版本。下载失败返回 `404 RESOURCE_NOT_FOUND` 或 `409 VERSION_NOT_DOWNLOADABLE`。

## 11. 轮询建议与主链路调用顺序

客户端建议每 2 秒轮询一次会话和任务状态；连续 5 次无变化后退避到 5 秒。以下顺序构成 V1 主链路：

```text
登录
  → 创建病例
  → 创建邀请码
  → 患者兑换邀请码
  → 医生启动会话
  → 保存 Q1–Q8
  → 提取/确认视觉特征
  → 创建首轮生成任务
  → 轮询生成和安全检查
  → 医生审核版本
  → 授权当前版本给 session_id
  → 患者读取已授权 Avatar
  → 患者提交调整（最多 3 次）
  → 医生审核调整
  → 创建新版本任务
  → 安全检查和医生审核
  → 重新授权
  → 医生查看/回退版本
  → 患者暂停或医生结束会话
  → 医生下载指定版本
```

## 12. 当前 Demo 路由兼容映射

以下接口只属于当前单机 Demo，不属于正式 V1 资源型 API：

```text
/api/sessions/{id}/profile
  → PUT /api/sessions/{session_id}/voice-features/{question_key}

/api/sessions/{id}/generate
  → POST /api/cases/{case_id}/generations

/api/sessions/{id}/revise
  → POST /api/patient-sessions/{session_id}/adjustment-requests
     + POST /api/adjustment-requests/{request_id}/review
     + POST /api/adjustment-requests/{request_id}/generate

/api/sessions/{id}/restore/{version}
  → POST /api/avatar-versions/{version_id}/rollback
```

正式开发不得把 Demo 路由、患者 token URL 参数、直接同步调用模型或患者直接调用 `/generate` 作为目标 V1 实现。

## 13. 主链路验收映射

| 验收点 | 必须可验证的接口 |
|-|-|
| 医生创建病例 | `POST /api/cases` |
| 患者兑换邀请码 | `POST /api/session-invites/redeem` |
| 医生启动会话 | `POST /api/sessions/{session_id}/start` |
| 保存 Q1–Q8 | `PUT /api/sessions/{session_id}/voice-features/{question_key}` |
| 生成并查询任务 | `POST /api/cases/{case_id}/generations`、`GET /api/generation-jobs/{job_id}` |
| 安全检查 | `GET /api/generation-jobs/{job_id}/safety-check` |
| 医生审核和授权 | `POST /api/avatar-versions/{version_id}/review`、`POST /api/avatar-versions/{version_id}/authorize` |
| 患者查看 Avatar | `GET /api/patient-sessions/{session_id}/avatar` |
| 患者调整 | `POST /api/patient-sessions/{session_id}/adjustment-requests` |
| 医生处理调整 | `POST /api/adjustment-requests/{request_id}/review`、`/generate` |
| 版本查看和回退 | `GET /api/cases/{case_id}/avatar-versions`、`POST /api/avatar-versions/{version_id}/rollback` |
| 安全暂停与恢复 | `POST /api/patient-sessions/{session_id}/pause`、`POST /api/sessions/{session_id}/resume` |
| 结束会话 | `POST /api/sessions/{session_id}/stop` |
| 下载指定版本 | `GET /api/cases/{case_id}/avatar-versions/{version_id}/download` |

所有越权访问、旧邀请码、旧凭证、结束后的旧页面、重复写请求、并发调整和未审核图片访问都必须有对应失败用例。

## 14. 受限管理员后台接口

以下接口均要求 `role=admin`。医生调用时统一按无权资源处理。响应不得包含研究编号、病例原文、Q1–Q8、患者调整原文、Prompt、模型参数或 Avatar 图片。

| 方法 | 路径 | 用途 | 幂等要求 |
|-|-|-|-|
| GET | `/api/admin/doctors` | 查看医生账户审批和启停状态 | 不需要 |
| PATCH | `/api/admin/doctors/{doctor_id}` | 审批、拒绝、启用或停用医生；停用立即撤销现有登录 | 必须 |
| GET | `/api/admin/risk-rules` | 查看当前后端风险规则 | 不需要 |
| PUT | `/api/admin/risk-rules/{rule_id}` | 更新规则并强制更新规则版本；只作用于新请求 | 必须 |
| GET | `/api/admin/stats` | 查看角色、病例/会话/调整/生成/删除任务聚合计数、生成成功率与耗时，以及脱敏运行告警 | 不需要 |
| GET | `/api/admin/audit-logs` | 查看经过字段白名单再次过滤的脱敏审计 | 不需要 |
| GET | `/api/admin/archived-cases` | 查看可恢复病例的脱敏引用和删除截止时间 | 不需要 |
| POST | `/api/admin/cases/{case_id}/restore` | 在到期前恢复为草稿；不恢复旧会话、不改变删除截止时间 | 必须 |
| GET | `/api/admin/retention-jobs` | 查看最小化删除任务状态和脱敏错误代码 | 不需要 |

删除任务由后台调度器执行，不提供绕过到期时间的公开触发接口。任务完成后解除病例引用，只保留不可逆病例摘要、删除类别计数、尝试次数、状态和完成时间。
