# Avatar 当前工程地图

- 文档版本：V1.2
- 当前状态：与 2026-07-30 项目目录同步

## 1. 根目录

```text
Avatar/
├── frontend/                 React 三角色前端
├── backend/                  FastAPI 后端、迁移、脚本和测试
├── infra/                    Docker、Nginx 和临时隧道脚本
├── docs/                     产品、架构、安全、AI 与质量文档
├── .github/workflows/        CI
├── .env.example              非敏感配置模板
├── docker-compose.yml        Compose 编排
├── netlify.toml              Netlify 前端部署配置
├── PROJECT-MAP.md
└── README.md
```

## 2. 前端

```text
frontend/
├── src/
│   ├── app/                  路由和应用入口
│   ├── components/           复用 UI、品牌、语言和状态组件
│   ├── i18n/                 English、简体中文、繁體中文文案
│   ├── lib/                  API 客户端与前端工具
│   ├── pages/                当前页面组件
│   │   ├── LandingPage.tsx
│   │   ├── DoctorApplicationPage.tsx
│   │   ├── DoctorLoginPage.tsx
│   │   ├── DoctorWorkspacePage.tsx
│   │   ├── DoctorCasePage.tsx
│   │   ├── DoctorInterviewPage.tsx
│   │   ├── PatientInvitePage.tsx
│   │   ├── PatientWaitingPage.tsx
│   │   ├── AdminLoginPage.tsx
│   │   └── AdminDashboardPage.tsx
│   └── styles/               设计令牌、布局和响应式样式
├── public/                   品牌和登录/首页图片资源
├── e2e/                      Playwright 业务与布局测试
├── package.json
└── vite.config.ts
```

前端负责页面呈现、输入交互、短轮询和权限路由，不负责：

- 保存 OpenAI API Key；
- 判定患者文本风险；
- 直接调用 GPT Image 2；
- 决定患者是否可以查看未授权图像。

## 3. 后端

```text
backend/
├── app/
│   ├── main.py               FastAPI 入口
│   ├── api/
│   │   ├── router.py         总路由
│   │   └── routes/           auth、cases、sessions、features、
│   │                         avatars、adjustments、admin 等
│   ├── adapters/
│   │   ├── feature_mapping/  确定性映射与 Prompt Builder
│   │   ├── image_generation/ GPT Image 2 Provider
│   │   └── storage/          本地与 S3 存储
│   ├── config/               环境配置
│   ├── domain/               状态枚举和领域规则
│   ├── models/               SQLAlchemy 实体
│   ├── observability/        日志与审计辅助
│   ├── repositories/         数据访问
│   ├── schemas/              Pydantic 请求响应契约
│   ├── security/             认证、哈希、加密和限流
│   ├── services/             业务服务、风险和生成编排
│   └── workers/              Celery 生成和留存任务
├── migrations/               Alembic
├── scripts/                  示例数据与线上验收脚本
├── tests/                    Pytest
└── pyproject.toml
```

## 4. 需求定位

| 需求 | 主要位置 |
|---|---|
| 医生申请、登录和管理员审批 | `backend/app/api/routes/auth.py`、`admin.py`、前端登录/管理员页 |
| 病例与归档 | `backend/app/api/routes/cases.py` |
| 邀请码和患者会话 | `invites.py`、`sessions.py` |
| Q1–Q8 | `features.py`、`backend/app/services/features.py` |
| 确定性视觉映射 | `backend/app/adapters/feature_mapping/deterministic_mapper.py` |
| Prompt 构建 | `backend/app/adapters/feature_mapping/prompt_builder.py` |
| GPT Image 2 生成 | `backend/app/adapters/image_generation/`、`backend/app/services/avatar_generation.py` |
| 图像版本、审核、授权、回退和下载 | `backend/app/api/routes/avatars.py` |
| 患者调整和医生可选改写 | `backend/app/api/routes/adjustments.py` |
| 多语言风险规则 | `backend/app/services/risk_engine.py`、`text_normalization.py` 与 `docs/safety/AI-SAFETY.md` |
| 数据模型 | `backend/app/models/entities.py` |
| 前端状态同步 | `frontend/src/pages/` 与 `frontend/src/lib/` |
| 三语言文案 | `frontend/src/i18n/` |
| 自动化测试 | `backend/tests/`、`frontend/e2e/` |

## 5. 运行形态

### 本地轻量开发

- Vite 前端；
- FastAPI；
- SQLite；
- 本地图像存储；
- 内联生成；
- 服务端配置 GPT Image 2 密钥。

### Docker Compose

- 静态前端容器；
- FastAPI；
- PostgreSQL；
- Redis；
- Celery Worker/Beat；
- MinIO；
- 服务端 GPT Image 2 配置。

### Netlify

Netlify 只构建和托管 `frontend/`。后端、数据库、Redis、对象存储、生成 Worker 和 OpenAI API Key 必须在独立环境运行。

## 6. 配置与密钥边界

- `.env.example` 只能保存变量名和非敏感示例；
- OpenAI、数据库、S3 和应用密钥不能提交到 GitHub；
- `VITE_*` 是公开前端构建变量，禁止放入任何密钥；
- 业务生图使用 `MODEL_PROVIDER=openai`、`MODEL_NAME=gpt-image-2`；
- 默认质量为 `MODEL_QUALITY=low`；
- 自动化测试替身只用于测试，不能写成当前业务 Provider。

## 7. 文档入口

- `docs/architecture/TECH.md`：当前技术架构；
- `docs/architecture/API.md`：当前 REST API；
- `docs/architecture/DATA.md`：当前 ORM 数据模型；
- `docs/safety/AI-SAFETY.md`：`RISK-V1.4` 风险策略与模型调用边界；
- `docs/safety/RISK-LEXICON.md`：多语言规范词、组合语义、规避形式和反误判基线；
- `docs/ai/voice-to-appearance-v1.md`：映射与 Prompt；
- `docs/quality/TEST.md`：测试矩阵；
- `docs/quality/ONLINE-ACCEPTANCE.md`：GPT Image 2 线上状态。
