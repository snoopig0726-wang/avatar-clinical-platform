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
