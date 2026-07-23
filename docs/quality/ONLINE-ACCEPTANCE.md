# 线上完整业务验收记录

- 验收日期：2026-07-23
- 前端：<https://keen-alpaca-5d954e.netlify.app>
- 后端：本机 Docker Compose 经 Cloudflare Quick Tunnel 临时映射
- 数据：仅使用自动生成的去标识化测试病例
- 图像生成：Mock Provider
- 独立语义安全：Mock 门禁；OpenAI `omni-moderation-latest` 适配器已就绪但未配置真实密钥

## 结论

医生端、受邀患者端和系统管理员端的线上闭环全部通过。验收病例最终已归档并进入既有 30 天保留流程；调试期间产生的三条匿名失败病例也已通过业务 API 归档。

## 已通过检查

1. Netlify 站点和后端就绪探针返回成功，PostgreSQL、Redis、MinIO、图像 Provider 与语义安全 Provider 均可用；
2. 医生与管理员分别登录，医生创建匿名病例及一次性邀请码；
3. 患者兑换邀请码，医生确认当面同意并启动监督会话；
4. 医生完整录入 Q1–Q8，系统完成确定性声音到视觉映射，医生确认后才允许生图；
5. 首次异步生成通过图片结构与独立语义门禁，医生审核前、授权前患者均看不到候选图；
6. 医生审核并明确授权后，患者取得短期签名 PNG；医生下载包只包含 `avatar.png` 和冻结的 `q1-q8.json`；
7. 患者提交安全调整，经医生审核后执行第二次异步生成；新图授权前患者继续看到旧图；
8. 危机表达被 `RISK-V1.0` 拦截并触发安全暂停，只有医生可以恢复；
9. 历史版本回退会撤销当前授权，重新审核与再次授权后才可展示；显式撤权立即生效；
10. 会话停止和结束、病例归档、管理员恢复及再次归档均成功，再次归档不延长原 30 天删除期限；
11. 管理员只能读取聚合统计和脱敏审计，返回内容不包含研究编号或患者风险原文；
12. 数据库中的成功版本保存了语义安全供应商、模型、请求标识和命中分类元数据。

## 验收中发现并修复的问题

- PostgreSQL 会立即检查新邀请码/新会话与审计记录之间的外键，现已在写审计前显式 `flush` 主记录；
- Celery 每次 `asyncio.run` 会创建新事件循环，复用 asyncpg 连接池导致第二次生成失败；Worker 现使用短生命周期 `NullPool` 会话，并新增连续事件循环回归测试。

## 复验命令

```powershell
python backend/scripts/online_acceptance.py `
  --api-base https://临时后端地址/api `
  --site-url https://keen-alpaca-5d954e.netlify.app `
  --doctor-password 演示医生密码 `
  --admin-password 演示管理员密码
```

Quick Tunnel 地址每次重启可能变化。该结果证明当前临时线上演示链路可用，不代表正式生产托管、真实 GPT Image 2 画质或真实 OpenAI Moderation 拦截效果已经验收。
