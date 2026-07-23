# 幻听患者个性化 Avatar 生成系统

面向临床医生的受监督 Avatar 生成平台。系统将医生录入的 Q1-Q8 结构化声音特征映射为低刺激、非身份化的视觉特征，经医生确认后生成候选头像，并通过图片安全检查、医生人工审核和会话授权后向受邀患者展示。

## 工程结构

```text
frontend/   React + TypeScript + Ant Design
backend/    FastAPI + SQLAlchemy + Celery
backend/tests/ 后端领域、API 和完整监督会话流程测试
infra/      Docker、网关和部署配置
docs/       产品、架构、安全、AI 映射和验收规范
```

文档入口见 [`docs/README.md`](docs/README.md)，目标目录职责见 [`PROJECT-MAP.md`](PROJECT-MAP.md)。

## 本地开发

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
cd backend
uvicorn app.main:app --reload
```

健康检查：`GET http://localhost:8000/api/health/live`

未配置 `.env` 时，本地开发默认使用 `backend/.local-data/avatar.db`，并创建仅用于本地联调的医生账户：

```text
邮箱：doctor@example.com
密码：Avatar-demo-2026

管理员后台：
邮箱：admin@example.com
密码：Avatar-admin-2026
```

该账户受 `BOOTSTRAP_DEMO_DATA` 控制，测试与生产环境必须关闭。正式部署继续使用 PostgreSQL。

本地启动还会幂等生成三组去标识化示例数据：

- `DEMO-VOICE-001`：会话进行中，Q1–Q8、视觉映射和医生确认均已完成；包含 Mock Avatar 授权和一条待医生审核的患者调整；
- `DEMO-VOICE-002`：患者已兑换邀请码，等待医生确认同意并开始；
- `DEMO-VOICE-003`：已创建尚未兑换的一次性邀请码，可用于患者端联调。

也可以手动重复执行以下命令；重复执行不会创建重复病例：

```powershell
cd backend
python -m scripts.seed_examples
```

执行数据库迁移：

```powershell
cd backend
alembic upgrade head
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：`http://localhost:5173`

### 基础设施

安装 Docker 后可在项目根目录运行：

```powershell
docker compose up --build
```

启动后访问 `http://localhost:5173`；管理员后台为 `http://localhost:5173/admin/login`；API 文档位于 `http://localhost:8000/api/docs`。Compose 同时启动 Celery Worker 和每小时执行一次的留存调度器。

当前已接入 GPT Image 2 适配器。未配置密钥时默认使用 Mock Provider，仍会完整执行异步任务、图片检查、MinIO 存储、医生审核和患者授权。正式联调前在项目根目录创建 `.env`：

```dotenv
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-...
SEMANTIC_IMAGE_SAFETY_PROVIDER=openai
```

GPT Image 2 与独立语义图片复检默认共用后端 `OPENAI_API_KEY`；如需隔离密钥，可另设 `SEMANTIC_IMAGE_SAFETY_API_KEY`。密钥只进入后端和 Worker，不会传到浏览器或写入数据库。生成任务只保存 Prompt 模板版本与摘要，不保存完整 Prompt。

### 自动验证

```powershell
cd backend
pytest
ruff check .

cd ..\frontend
npm run typecheck
npm run build

# Docker 服务启动后，使用本机 Edge 验证公开入口、医生登录和管理员总览
npm run test:e2e

# 对已部署站点执行医生、患者、管理员完整业务验收
python backend/scripts/online_acceptance.py --api-base https://你的后端地址/api --site-url https://你的站点.netlify.app --doctor-password 演示医生密码 --admin-password 演示管理员密码
```

仓库同时提供 `.github/workflows/ci.yml`，在每次推送和合并请求中执行后端测试、前端构建及容器化浏览器测试。

## Netlify 上线

仓库根目录已提供 `netlify.toml`，Netlify 可直接识别 `frontend/` 的构建和 React Router 回退规则。三种角色页面由同一个前端站点承载：

- 医生端：`/doctor/*`
- 受邀患者端：`/patient/*`
- 系统管理员端：`/admin/*`

在 Netlify 中设置公开构建变量：

```text
VITE_API_BASE_URL=https://你的后端域名/api
```

Netlify 仅承载静态前端。FastAPI、Celery Worker/Beat、PostgreSQL、Redis、S3 兼容对象存储和 GPT Image 2 密钥必须部署到独立后端环境，不能把密钥放进任何 `VITE_*` 变量。完整发布顺序和生产检查清单见 [`docs/architecture/NETLIFY-DEPLOYMENT.md`](docs/architecture/NETLIFY-DEPLOYMENT.md)。

## 当前阶段

当前已经打通医生账户申请、本地开发邮箱验证、管理员审批、登录、病例与监督会话、Q1–Q8、声音到视觉映射、患者调整风险拦截与医生审核，以及管理员规则维护、聚合统计、运行告警、脱敏审计、归档恢复和30天到期永久删除。公开高风险入口使用 Redis 匿名化限流；病例关键写操作使用 PostgreSQL 行锁保护并发状态。GPT Image 2、Celery 生成状态机、MinIO 图片存储、独立语义图片安全复检、医生审核与患者授权、历史版本重新审核回退、不可变版本快照和指定版本下载审计已经实现；未提供 OpenAI Key 时由 Mock Provider 生成联调图片并执行可控 Mock 语义门禁。患者原文加密保存且不会直接进入模型；风险拦截原文和完整生图 Prompt 均不落库。

当前实现状态见 [`docs/decisions/IMPLEMENTATION-STATUS.md`](docs/decisions/IMPLEMENTATION-STATUS.md)。
