# 目标 V1 工程地图

- 所属产品：幻听患者个性化 Avatar 生成系统
- 关联 PRD：https://ycnhe29l1vtr.feishu.cn/docx/JAY0d7gkgoVAAjxa8vVcoQK1nKc
- 文档版本：V1.0
- 文档状态：Draft
- 来源：PRD V3.0 审查修订

## 1. 使用范围

本文件只描述目标 V1 工程结构，不描述当前单机 Demo 的 `app/`、SQLite 或本地 SVG 实现。目标 V1 采用前后端分离、PostgreSQL、Redis、Celery、S3 兼容对象存储和模型适配器架构。

## 2. 目标目录树

```text
avatar-v1/
├── frontend/
│   ├── src/
│   │   ├── app/                 # 路由、全局状态、权限守卫
│   │   ├── pages/
│   │   │   ├── doctor/          # 医生工作台、病例、生成、版本和审核
│   │   │   ├── patient/         # 患者邀请码和受监督会话
│   │   │   └── admin/           # 管理员账户、规则、统计和审计
│   │   ├── components/          # 复用 UI 组件和状态组件
│   │   ├── services/            # API client、轮询和任务状态订阅
│   │   ├── types/               # 前端 DTO 和状态类型
│   │   └── styles/              # 主题、可访问性和布局样式
│   ├── public/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── api/                 # 路由、依赖和请求响应模型
│   │   │   ├── auth.py
│   │   │   ├── cases.py
│   │   │   ├── sessions.py
│   │   │   ├── avatars.py
│   │   │   ├── adjustments.py
│   │   │   └── admin.py
│   │   ├── domain/              # 领域状态、权限和业务规则
│   │   ├── services/            # 病例、会话、版本、风险和下载服务
│   │   ├── workers/             # Celery 任务和重试策略
│   │   ├── adapters/            # 外部服务适配器
│   │   │   ├── feature_mapping/
│   │   │   ├── image_generation/
│   │   │   ├── image_safety/
│   │   │   └── storage/
│   │   ├── models/              # SQLAlchemy 数据模型
│   │   ├── schemas/             # Pydantic DTO 和校验
│   │   ├── repositories/        # 数据库访问和事务边界
│   │   ├── security/            # JWT、会话、设备绑定和密钥读取
│   │   ├── config/              # 环境配置和 feature flags
│   │   └── observability/       # 日志、指标、追踪和告警
│   ├── migrations/              # Alembic 迁移
│   └── pyproject.toml
├── tests/
│   ├── unit/                    # 领域规则、映射和适配器单测
│   ├── integration/             # 数据库、Redis、对象存储和 Worker 集成测试
│   ├── api/                     # API 权限、状态和幂等测试
│   └── e2e/                     # 医生/患者/管理员关键流程测试
├── infra/
│   ├── docker/                  # Dockerfile 和 Compose 配置
│   ├── nginx/                   # 网关和 TLS 配置
│   └── deploy/                  # 测试/生产部署清单
├── docs/                        # 设计、运行手册和决策记录
├── .env.example                 # 非敏感配置模板
├── docker-compose.yml           # 本地和测试依赖编排
├── PROJECT-MAP.md
└── README.md
```

## 3. 模块职责地图

| 需求 | 主要位置 | 不应直接修改 |
|-|-|-|
| 医生病例和邀请码 | `backend/app/api/cases.py`、`sessions.py`、`services/` | 模型适配器、前端页面中的权限判断 |
| 患者会话状态和安全暂停 | `sessions.py`、`domain/`、`frontend/src/pages/patient/` | 数据库表外直接存状态 |
| Avatar 版本、审核和回退 | `avatars.py`、版本服务、`frontend/src/pages/doctor/` | 供应商 SDK |
| 患者调整次数和审核 | `adjustments.py`、风险服务、调整页面 | 患者端直接调用模型 |
| 模型接入 | `backend/app/adapters/`、`workers/` | 业务路由中硬编码供应商请求 |
| 风险规则和图片安全 | `domain/`、`services/`、`adapters/image_safety/` | 前端单独决定是否放行 |
| 数据表和迁移 | `models/`、`repositories/`、`migrations/` | 运行时自动改表 |
| 监控和审计 | `observability/`、`audit` 服务 | 记录患者原文、Prompt 或图片内容 |
| 30 天删除 | `workers/`、留存服务、`storage/` | 只删除数据库而不删除对象存储和备份 |

## 4. 入口与运行命令

目标 V1 的入口和命令约定如下：

```text
本地 API：       backend/app/main.py
前端开发：       frontend/ 开发服务器
异步 Worker：    backend/app/workers/
数据库迁移：     backend/migrations/（Alembic）
本地依赖：       docker-compose.yml
```

开发、测试和部署命令应由根目录 `README.md` 统一维护，至少包含：安装依赖、启动本地依赖、启动 API、启动 Worker、执行迁移、运行单元/集成/E2E 测试和查看健康检查。

## 5. 配置和密钥边界

- `.env.example` 只包含变量名和安全示例值；
- 真实 API Key、数据库密码、S3 密钥和 JWT 密钥只进入密钥管理服务或部署环境；
- 浏览器只获得业务 API 凭证，不获得模型或对象存储长期密钥；
- Provider、模型名称、超时、重试和留存天数均通过服务端配置注入。

## 6. 文档关系

- `TECH.md`：整体架构、技术栈、部署、任务和模型适配原则；
- `DATA.md`：数据库实体、版本、权限、留存和删除字段；
- `API.md`：外部 API 路径、权限、错误和幂等契约；
- `AI-SAFETY.md`：V1 表单映射、禁止元素和安全门禁；
- `TEST.md`：角色、会话、调整、版本、删除和安全测试矩阵；
- `PROJECT-MAP.md`：本文件，负责目标 V1 代码目录和模块定位。
