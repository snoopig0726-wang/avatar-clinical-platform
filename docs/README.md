# Avatar V1 文档中心

本目录保存“幻听患者个性化 Avatar 生成系统”V1 的产品、技术、安全、AI 映射与测试规范。

所有规范文件同等重要。目录顺序不代表优先级；当文档之间出现差异时，应结合产品目标、临床安全、技术可实现性和验收要求综合处理，并把最终结论记录到 [`decisions/PRODUCT-DECISIONS.md`](decisions/PRODUCT-DECISIONS.md)。

## 文档分类

### 产品

- [`product/幻听患者个性化Avatar生成系统-PRD-V3.0.pdf`](product/幻听患者个性化Avatar生成系统-PRD-V3.0.pdf)：V1 产品范围、角色、主流程、视觉映射、安全边界和数据生命周期。

### 工程与架构

- [`../PROJECT-MAP.md`](../PROJECT-MAP.md)：目标 V1 工程地图、目录职责和依赖边界。
- [`architecture/TECH.md`](architecture/TECH.md)：总体架构、技术栈、异步任务、适配器与部署方案。
- [`architecture/API.md`](architecture/API.md)：REST API、认证、权限、状态、幂等和错误契约。
- [`architecture/DATA.md`](architecture/DATA.md)：PostgreSQL 数据模型、版本快照、审计、加密与删除任务。

### 安全

- [`safety/AI-SAFETY.md`](safety/AI-SAFETY.md)：正式版患者调整文本风险拦截规则及后端模型调用边界。

### AI 映射与 Prompt

- [`ai/voice-to-appearance-v1.md`](ai/voice-to-appearance-v1.md)：Q1-Q8 与医生确认结果到统一生图 Prompt 的规范。
- [`ai/reference/feature_mapping_prompt.py`](ai/reference/feature_mapping_prompt.py)：Prompt Builder 参考代码，不作为完整业务流程或运行时代码直接导入。

### 测试与验收

- [`quality/TEST.md`](quality/TEST.md)：P0/P1/P2 测试矩阵、黑盒安全用例、证据要求和上线闸门。

### 决策记录

- [`decisions/PRODUCT-DECISIONS.md`](decisions/PRODUCT-DECISIONS.md)：对话中已经确认的跨文档口径和实现基线。
- [`decisions/IMPLEMENTATION-STATUS.md`](decisions/IMPLEMENTATION-STATUS.md)：已完成、暂缓和下一阶段开发范围。

## 建议阅读路径

以下顺序仅用于快速建立上下文，不表示规范优先级：

1. 阅读产品 PRD 和已确认决策。
2. 阅读根目录工程地图与总体技术方案。
3. 按任务阅读 API、DATA、安全或 AI 映射规范。
4. 开发前查阅对应 TEST 用例，开发后保留可复核证据。

## 维护约定

- 原始规范内容保持稳定；明确修改时同步更新文档版本。
- 跨文档规则变更必须同步检查 API、数据模型、测试用例和 Prompt 模板。
- Prompt、风险规则和图片安全检查器必须记录版本号。
- 参考代码放在 `reference/` 下，不得绕过领域服务、医生确认或安全门禁直接接入生产流程。
- 真实密钥、患者身份信息、患者调整原文、图片和完整 Prompt 不得写入普通日志或审计日志。
