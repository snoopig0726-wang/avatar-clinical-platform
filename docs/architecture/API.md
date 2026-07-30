# API 契约

- 文档版本：V1.2
- 当前状态：与 2026-07-30 FastAPI 路由同步
- 基础路径：`/api`
- 实现依据：`backend/app/api/router.py` 与 `backend/app/api/routes/`

## 1. 通用约定

### 1.1 身份认证

- 医生和管理员：`Authorization: Bearer <access_token>`
- 患者：`X-Session-Token: <patient_session_token>`，同时验证设备绑定信息
- 浏览器及客户端不得持有 OpenAI API Key

### 1.2 幂等

创建、更新、审核、授权、回退、归档等写操作使用：

```http
Idempotency-Key: <client-generated-key>
```

服务端以调用者范围、操作名称和幂等键保存 `idempotency_records`。重复提交相同请求返回原资源；相同键对应不同请求体时拒绝。

### 1.3 错误响应

错误响应使用稳定的业务错误码和面向当前语言的安全提示，不向患者暴露 Provider 错误、风险命中原文、Prompt 或服务端密钥。

## 2. 健康与契约

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health/live` | 进程存活 |
| GET | `/api/health/ready` | 数据库等依赖就绪 |
| GET | `/api/meta/contracts` | 前后端契约元信息 |
| GET | `/api/meta/voice-feature-contract` | Q1–Q8 题目顺序和受控枚举 |

运行时 Prompt 模板版本为 `voice-to-appearance-v1.1`。若 `/api/meta/contracts` 暂时仍返回旧版本，应以运行时生成记录的 `prompt_template_version` 为准，并修正元数据端点后再发布。

## 3. 员工认证

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/auth/doctor-applications` | 医生申请 |
| POST | `/api/auth/verify-email` | 邮箱验证 |
| POST | `/api/auth/login` | 医生或管理员登录 |
| POST | `/api/auth/logout` | 注销并撤销访问会话 |
| GET | `/api/users/me` | 当前员工摘要 |

## 4. 病例与邀请码

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/cases` | 医生病例列表 |
| POST | `/api/cases` | 创建病例 |
| GET | `/api/cases/{case_id}` | 病例详情 |
| POST | `/api/cases/{case_id}/archive` | 归档病例 |
| GET | `/api/cases/safety-events/recent` | 医生最近安全事件 |
| POST | `/api/cases/{case_id}/session-invites` | 创建一次性邀请码 |
| GET | `/api/cases/{case_id}/session-invites` | 邀请码及会话列表 |
| DELETE | `/api/session-invites/{invite_id}` | 撤销未使用邀请码 |
| POST | `/api/session-invites/redeem` | 患者兑换邀请码 |

每次成功兑换都会创建新的 `patient_sessions`。同一病例的新会话不继承旧会话的 Q1–Q8、满意状态或 3 次调整计数。

## 5. 会话

| 方法 | 路径 | 角色 | 用途 |
|---|---|---|---|
| GET | `/api/sessions/{session_id}` | 医生/当前患者 | 读取会话状态 |
| POST | `/api/sessions/{session_id}/start` | 医生 | 确认知情同意并启动 |
| POST | `/api/patient-sessions/{session_id}/pause` | 当前患者 | 报告不适并安全暂停 |
| POST | `/api/sessions/{session_id}/resume` | 医生 | 处理后恢复会话 |
| POST | `/api/sessions/{session_id}/stop` | 医生 | 结束会话 |
| POST | `/api/patient-sessions/{session_id}/avatar-feedback` | 当前患者 | 记录满意或进入调整 |

前端通过短轮询刷新状态。患者不适、敏感输入、生成进度、满意、暂停、恢复和结束等状态应在下一次轮询自动出现，不要求手动刷新。

## 6. Q1–Q8 与视觉特征

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/cases/{case_id}/voice-features` | 读取病例最新会话的答案 |
| GET | `/api/sessions/{session_id}/voice-features` | 读取指定会话答案 |
| PUT | `/api/sessions/{session_id}/voice-features/{question_key}` | 保存单题答案 |
| POST | `/api/cases/{case_id}/extract-features` | 从指定声音描述映射视觉特征 |
| GET | `/api/cases/{case_id}/visual-features` | 读取当前视觉特征 |
| PUT | `/api/cases/{case_id}/visual-features` | 医生确认或修改受控特征 |

新会话重新录入 Q1–Q8 后，生图按钮必须依据该会话对应的 `sound_description` 和 `visual_feature` 判断，不能因为病例已有旧图就显示旧的生成进度。

## 7. GPT Image 2 生图与版本

### 7.1 创建生成

```http
POST /api/cases/{case_id}/avatar-generations
```

请求体：

```json
{
  "mode": "initial"
}
```

`mode` 可为：

- `initial`
- `same_features_regenerate`
- `feature_update`

响应状态为 `202`，响应对象是 `AvatarVersionResponse`，包含 `version_id`、`generation_status`、Provider 元数据、安全状态和图像地址等。当前接口不返回独立 `job_id`。

当前运行配置：

- Provider：OpenAI
- 模型：`gpt-image-2`
- 默认质量：`low`
- Prompt 模板：`voice-to-appearance-v1.1`

### 7.2 查询和控制

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/cases/{case_id}/avatar-versions` | 列出版本及生成状态 |
| GET | `/api/cases/{case_id}/avatar-versions/{version_id}` | 单版本详情 |
| POST | `/api/avatar-versions/{version_id}/cancel` | 取消尚未完成的生成 |
| POST | `/api/avatar-versions/{version_id}/review` | 医生审核 |
| POST | `/api/avatar-versions/{version_id}/authorize` | 授权患者查看 |
| POST | `/api/avatar-versions/{version_id}/rollback` | 选择历史版本回退 |
| POST | `/api/avatar-versions/{version_id}/delete` | 删除未授权的图像版本 |
| POST | `/api/cases/{case_id}/authorization/revoke` | 撤销当前授权 |
| GET | `/api/cases/{case_id}/avatar-versions/{version_id}/download` | 下载指定版本 |

生成、安全检查和审核状态都保存在 `avatar_versions`。当前不存在：

- `POST /api/cases/{case_id}/generations`
- `GET /api/generation-jobs/{job_id}`
- `GET /api/generation-jobs/{job_id}/safety-check`

这些是早期设计接口，不得再用于前端或验收文档。

## 8. 患者查看与调整

| 方法 | 路径 | 角色 | 用途 |
|---|---|---|---|
| GET | `/api/patient-sessions/{session_id}/avatar` | 当前患者 | 读取已授权图像和过程状态 |
| POST | `/api/patient-sessions/{session_id}/adjustment-requests` | 当前患者 | 提交调整建议 |
| GET | `/api/patient-sessions/{session_id}/adjustment-requests` | 当前患者 | 查看自己的处理状态 |
| GET | `/api/cases/{case_id}/adjustment-requests` | 医生 | 查看病例的调整建议 |
| POST | `/api/adjustment-requests/{request_id}/remap-preview` | 医生 | 改写患者原话并预览重新映射结果 |
| POST | `/api/adjustment-requests/{request_id}/review` | 医生 | 接受系统研判、接受医生改写或拒绝 |
| POST | `/api/adjustment-requests/{request_id}/generate` | 医生 | 按已批准受控指令生成新版本 |

患者提交示例：

```json
{
  "instruction": "背景更暗一些，眼神更坚定"
}
```

医生可选改写预览：

```json
{
  "clinician_edited_instruction": "适度降低背景亮度，保持眼神清晰坚定且避免压迫感"
}
```

受控映射对简体中文、繁体中文和英文输入生效。患者原文和医生改写都必须经过 `RISK-V1.3` 检查；风险命中时不能继续生成。刀具、锐器或创口与血液描述即使被标点、空格或中英文变体拆开，也必须被后端组合规则拦截。

调整额度按 `session_id` 计算，每个会话最多 3 次。新邀请码产生的新会话从 0/3 开始。

## 9. 管理员接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/doctors` | 医生账号列表 |
| PATCH | `/api/admin/doctors/{doctor_id}` | 审批、拒绝、启用或停用医生 |
| GET | `/api/admin/risk-rules` | 风险规则列表 |
| PUT | `/api/admin/risk-rules/{rule_id}` | 更新风险规则 |
| GET | `/api/admin/stats` | 脱敏聚合统计 |
| GET | `/api/admin/audit-logs` | 脱敏审计日志 |
| GET | `/api/admin/archived-cases` | 可恢复归档病例摘要 |
| POST | `/api/admin/cases/{case_id}/restore` | 到期前恢复病例 |
| GET | `/api/admin/retention-jobs` | 留存删除任务 |

管理员响应不得包含病例正文、Q1–Q8、患者调整原文、Prompt、模型参数、图像或 API Key。

## 10. 推荐主链路

```text
员工登录
→ 创建病例
→ 创建邀请码
→ 患者兑换并创建新会话
→ 医生启动会话
→ 保存本会话 Q1–Q8
→ 映射并确认视觉特征
→ POST /avatar-generations
→ 轮询 /avatar-versions
→ 医生审核并授权
→ 患者满意，或提交本会话内最多 3 次调整
→ 医生直接接受、可选改写后接受，或填写理由拒绝
→ 必要时生成、审核并重新授权
→ 医生结束会话
→ 患者确认结束提示后返回患者登录页
```
