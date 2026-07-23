# Netlify 上线说明

## 部署边界

Netlify 只部署 `frontend/` 中的 React 单页应用。医生端、受邀患者端和系统管理员端是同一个前端构建中的三组受保护路由，不是三套独立站点。

以下服务不能由这次 Netlify 静态站点部署替代，必须部署在独立、长期运行的后端环境：

- FastAPI API；
- Celery Worker 与定时清理任务；
- PostgreSQL；
- Redis；
- S3 兼容的私有对象存储；
- GPT Image 2 的后端密钥与调用逻辑。

浏览器只持有公开的 API 地址。OpenAI 密钥、数据库凭据、对象存储密钥不得写入 `VITE_*` 变量，因为这类变量会进入公开的前端产物。

## Netlify 配置

仓库根目录的 `netlify.toml` 已配置：

- Base directory：`frontend`
- Build command：`npm run build`
- Publish directory：`frontend/dist`
- React Router 的 SPA 回退；
- 基础安全响应头和带哈希静态资源的长期缓存。

在 Netlify 的 Site configuration → Environment variables 中设置：

```text
VITE_API_BASE_URL=https://api.example.com/api
```

该地址必须是公开 HTTPS 地址，末尾保留 `/api`，不要填写 OpenAI Key。

## 零费用临时演示方案

短期演示可以使用 Netlify Free + Cloudflare Quick Tunnel，让 Netlify 前端访问本机 Docker 中的后端服务。该方案不要求购买域名，也不要求 Cloudflare 账户。

项目需要两个临时隧道：

- FastAPI：本机 `8000` → 临时 HTTPS API 地址；
- MinIO API：本机 `9000` → 临时 HTTPS 图片地址。

PostgreSQL、Redis 和 MinIO Console 不通过隧道公开。MinIO 桶仍保持私有，网页只使用后端签发的短期图片 URL。

首次使用时安装免费客户端：

```powershell
winget install --id Cloudflare.cloudflared --exact
```

先启动 Docker，然后把实际 Netlify 站点地址传给辅助脚本：

```powershell
docker compose up -d
.\infra\tunnel\start-demo-tunnels.ps1 -NetlifyOrigin https://your-site.netlify.app
```

脚本会：

1. 启动 API 和图片存储两个 Quick Tunnel；
2. 把 Netlify 精确来源加入 FastAPI CORS；
3. 让后端生成可从公网访问的短期 MinIO 图片 URL；
4. 重启 API、Worker 和 Scheduler；
5. 输出要填写到 Netlify 的 `VITE_API_BASE_URL`。

在 Netlify 更新该变量并重新部署后即可演示。结束时运行：

```powershell
.\infra\tunnel\stop-demo-tunnels.ps1
```

此方案只适合短期展示：

- 电脑、Docker 和两个 `cloudflared` 进程必须持续运行；
- 每次重启隧道都会产生新地址，需要更新 Netlify 环境变量并重新部署；
- Quick Tunnel 没有可用性保证，不能作为正式生产后端；
- 本方案不会让 PostgreSQL 或 Redis 直接暴露到公网。

## 后端生产配置

后端环境至少应使用以下生产口径：

```dotenv
APP_ENV=production
AUTO_CREATE_TABLES=false
BOOTSTRAP_DEMO_DATA=false
BOOTSTRAP_EXAMPLE_DATA=false
FRONTEND_ORIGINS=https://your-site.netlify.app
GENERATION_DISPATCH_MODE=celery
MODEL_PROVIDER=openai
MODEL_NAME=gpt-image-2
MODEL_API_KEY=由后端密钥管理服务提供
SEMANTIC_IMAGE_SAFETY_PROVIDER=openai
SEMANTIC_IMAGE_SAFETY_MODEL=omni-moderation-latest
SEMANTIC_IMAGE_SAFETY_API_KEY=由后端密钥管理服务提供
```

同时替换 `SECRET_KEY`、数据库、Redis、S3 的所有本地默认值，启用 HTTPS，并在发布前执行：

```powershell
cd backend
alembic upgrade head
```

如果绑定正式域名，应把 `FRONTEND_ORIGINS` 更新为正式域名；需要同时保留 Netlify 域名时，可按后端配置支持的列表格式加入两个精确来源。不要使用 `*`。

## 发布顺序

1. 先部署 PostgreSQL、Redis、S3、API、Celery Worker 和定时任务。
2. 对后端执行迁移，检查 `/api/health/live` 和 `/api/health/ready`。
3. 在 Netlify 设置 `VITE_API_BASE_URL` 后连接 Git 仓库并发布。
4. 将 Netlify 正式域名加入后端 `FRONTEND_ORIGINS`，重启 API。
5. 用医生、邀请码患者、管理员三种角色各完成一次生产冒烟测试。

## 上线前必须验证

- 患者无法访问医生病例列表、历史版本和下载接口；
- 管理员只能查看聚合数据与脱敏审计，不能查看病例原文和 Avatar 图片；
- 生成中可取消，失败可重试，旧的已审核版本不受影响；
- 未经医生审核和授权的图片不会出现在患者端；
- 归档后 30 天永久删除任务在 Worker/定时器环境中实际运行；
- 日志、监控和错误追踪不记录邀请码、患者原文、完整 Prompt 或密钥。
