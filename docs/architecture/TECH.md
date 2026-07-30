# 技术方案

- 文档版本：V1.2
- 当前状态：与 2026-07-30 项目实现同步

## 1. 当前技术边界

系统面向医生、受邀患者和管理员三类角色。患者不建立长期账户，系统不接入医院病历系统。浏览器只调用项目后端，OpenAI API Key 不进入前端。

当前真实图像生成链路已经接入 OpenAI GPT Image 2，不再以占位图片或本地模拟结果代表业务生图成功。

## 2. 系统结构

```text
React / TypeScript / Ant Design
              |
         FastAPI REST API
              |
  领域服务、鉴权、风险检查、审计
       |                  |
PostgreSQL/SQLite      Redis/Celery
       |                  |
本地或 S3 对象存储   GPT Image 2 适配器
```

本地轻量开发可使用 SQLite、本地文件存储和内联生成；Docker Compose 形态使用 PostgreSQL、Redis、Celery 和 MinIO。两种形态共享同一套业务服务和数据库模型。

## 3. 当前技术栈

| 层级 | 实现 | 说明 |
|---|---|---|
| 前端 | React 19、TypeScript、Ant Design 6、React Router 7 | 医生、患者、管理员三端页面及三语言界面 |
| 构建 | Vite 8 | 本地开发、类型检查和生产构建 |
| 端到端测试 | Playwright | 桌面与移动端、多语言和核心流程 |
| 后端 | FastAPI、Python 3.11+、Pydantic 2 | REST API、鉴权、业务编排和 OpenAPI |
| ORM/迁移 | SQLAlchemy 2 AsyncIO、Alembic | SQLite/PostgreSQL 数据访问和迁移 |
| 数据库 | 本地可用 SQLite；Compose 使用 PostgreSQL 16 | 病例、会话、版本、调整、规则和审计 |
| 队列 | Celery + Redis | Compose 环境的异步生成与调度 |
| 图像存储 | 本地文件或 S3/MinIO | 由存储适配器隔离 |
| 图像生成 | OpenAI SDK + `gpt-image-2` | 当前业务生图 Provider |
| 语义图像安全 | 独立安全适配器 | 与 GPT Image 2 生图调用分离配置 |
| 部署 | Netlify 前端 + 可达的 FastAPI 后端；或 Docker Compose | Netlify 不托管本地数据库和常驻后端 |

## 4. 前端模块

- 首页与医生、患者、管理员登录页；
- 医生工作台、病例详情、邀请码和会话控制；
- Q1–Q8 录入、视觉特征确认和页面内直接生成；
- 图像版本审核、授权、下载、删除和回退；
- 患者等待、生成中、图像满意/调整、暂停和会话结束体验；
- 管理员医生审批、风险规则、统计、审计与归档恢复；
- English、简体中文、繁體中文三语言切换。

患者页和医生页使用短轮询同步会话、风险事件、调整和生成状态，因此状态更新不依赖手动刷新。

## 5. 后端领域模块

- `auth`：员工申请、邮箱验证、登录、访问会话和撤销；
- `cases`：病例、归档、恢复和留存计时；
- `invites` / `sessions`：邀请码、设备绑定、知情同意和会话状态；
- `features`：Q1–Q8、视觉特征映射和医生确认；
- `avatars`：GPT Image 2 生成、版本状态、安全、审核、授权和下载；
- `adjustments`：患者调整、多语言风险检查、医生可选改写、重新映射和生成；
- `admin`：账号、规则、统计、审计和留存任务；
- `storage`：本地或 S3 图像存储；
- `workers`：Celery 生成任务和调度任务。

## 6. GPT Image 2 接入

### 6.1 适配器边界

业务服务通过统一图像生成接口调用 Provider。OpenAI SDK 只出现在服务端适配层，路由和前端不直接依赖 SDK。

当前生产/联调配置：

```env
MODEL_PROVIDER=openai
MODEL_NAME=gpt-image-2
MODEL_QUALITY=low
MODEL_API_KEY=<server-side-secret>
```

`MODEL_API_KEY` 或兼容映射的 `OPENAI_API_KEY` 只在后端进程和生成 Worker 中读取。GitHub、Netlify 前端变量和浏览器网络响应都不能包含密钥。

### 6.2 Prompt 和快照

- Prompt 模板版本：`voice-to-appearance-v1.1`
- 输入：医生确认后的受控视觉特征，以及经医生审核的受控调整指令
- 数据库保存：Provider、模型、请求 ID、模板版本、Prompt SHA-256、输入快照和输出元数据
- 数据库不保存：完整 Prompt、API Key

### 6.3 生成状态

当前没有独立 `generation_jobs` 表。`avatar_versions` 自身记录：

- 生成模式和轮次；
- `generation_status`；
- 图像对象键；
- Provider 元数据；
- 安全状态；
- 医生审核状态；
- 失败代码和时间。

本地配置可使用 `GENERATION_DISPATCH_MODE=inline`，Docker Compose 使用 `celery`。两种模式返回相同的 `AvatarVersionResponse`，前端通过版本接口轮询。

### 6.4 自动化测试

自动化测试通过可控的测试替身覆盖成功、超时、安全阻断、无效图像和 Provider 失败等分支，以避免测试套件产生真实生图费用。测试替身只属于测试机制，不代表当前业务运行 Provider。

## 7. 风险与安全

- 患者调整和医生改写都执行 `RISK-V1.4`；
- 支持简体中文、繁体中文和英文输入；
- Unicode、大小写、空白、标点和简繁体变体先归一化再判定；
- 风险命中不进入生图；
- 图像生成后仍需图像安全检查和医生审核；
- 未授权版本患者不可见；
- 患者不适会暂停会话，只有医生处理后才能恢复。

完整规则见 `docs/safety/AI-SAFETY.md`。

## 8. 会话级状态

同一病例可以创建多次独立会话。以下状态均按 `session_id` 计算：

- Q1–Q8；
- 视觉特征来源；
- 患者满意版本；
- 每会话最多 3 次调整；
- 暂停、恢复和结束；
- 患者可见授权。

因此创建新邀请码并兑换后，调整额度回到 0/3，生成入口依据新会话特征重新判断。

## 9. 环境与部署

### 9.1 本地轻量运行

- FastAPI
- SQLite
- 本地图像目录
- 内联生成
- Vite 开发服务器

适合 UI 调整和单机联调。真实 GPT Image 2 调用仍需服务端 API Key。

### 9.2 Docker Compose

- FastAPI
- PostgreSQL
- Redis
- Celery Worker/Beat
- MinIO
- 静态前端容器

若使用 Compose 进行真实生图，必须显式设置 `MODEL_PROVIDER=openai` 和服务端密钥，不能依赖模板中的安全测试默认值。

### 9.3 Netlify

Netlify 部署静态前端，`VITE_API_BASE_URL` 指向可从公网访问的 FastAPI 地址。若后端仍运行在个人电脑上，临时隧道关闭、电脑待机、网络切换或后端进程退出都会导致线上登录与生图不可用。

要让朋友稳定测试并统一消耗项目方的 OpenAI 额度，应将后端部署到持续运行的服务器，并只在那里配置 API Key。

## 10. 当前已知差异

- 运行时 Prompt 已是 `voice-to-appearance-v1.1`，但 `/api/meta/contracts` 的旧版本值仍需同步修正。
- 移动端英文首页仍有一项标题裁切的端到端测试失败，发布前应修复。
- 语义图像安全是独立 Provider 配置，不能把它的测试配置误写成 GPT Image 2 生图状态。
