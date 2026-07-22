## 项目说明

### 文件与代码组织
1. 避免继续增大超大文件；超过 1500 行的文件只做小修。新增功能优先拆到独立 helper、hook、service、projection、renderer 或子组件。
2. `store` 文件只保留状态编排和 action 入口；事件解析、SSE 处理、block 合并、session 快照、DOM 工具函数应拆出。

### 前端约束
1. 用户可见 UI 优先复用 `frontend/src/components/ui`，样式优先使用 `frontend/src/styles/global.css` token 和 Tailwind 主题变量。
2. 新增或修改用户可见文案时，必须同步更新 `frontend/src/i18n/locales/zh-CN.json` 和 `frontend/src/i18n/locales/en-US.json`，不要在组件中硬编码中英文。
3. 新组件必须同时适配亮色和暗色模式，使用 `useIsDarkMode` 或主题变量处理背景、边框、文字及交互状态。
4. 视觉风格保持克制的 macOS 风格：玻璃感、柔和阴影、清晰层级、统一圆角和细边框；避免高饱和大渐变和营销式布局。
5. 不要写一些字符串匹配的硬性编码来实现流程从而解决很小一个场景的代码
6. 修复BUG应当从源头上解决而不是兜底性质的

### 后端约束
1. 注意后端服务是容器启动单实例但是拉起的多个 Python worker 进程实现的，所以得考虑多进程的问题
2. API endpoint 只做参数校验、权限校验和 service 调用；复杂业务逻辑必须放到 `services`。
3. 数据访问走 repository，请求/响应结构走 schema；不要在 service 中随意拼接长期使用的 dict 合同。
4. 新增或修改数据库字段时，必须补 Alembic migration，以及对应 repository、service、API 测试。
5. 涉及积分扣费、usage log、生成任务、agent run 状态的改动，必须考虑幂等、失败回滚、重复 SSE 连接、用户中断和重试。
8. 不要写一些字符串匹配的硬性编码来实现流程从而解决很小一个场景的代码
9. 修复BUG应当从源头上解决而不是兜底性质的

### 测试与验证
1. 后端改动优先运行相关 `pytest`；前端改动优先运行相关 `vitest`；涉及类型或构建边界时运行 `npm run build`。
2. 修 bug 时优先补回归测试；如果不补，必须说明风险为何可接受。
3. 如果未运行测试，最终说明中必须明确列出未运行项及原因。

### 安全与配置
1. 不要读取、打印或提交 `.env`、密钥、token、license、云凭证和用户隐私文件。
2. 不要把真实 API key、模型密钥或授权 token 写入测试、文档、日志或默认配置。
3. 日志中不要输出完整 prompt、用户文件内容、图片签名 URL、Authorization header、cookie 或敏感路径。

## Agent skills

### Issue tracker

Issues are tracked as local markdown files in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

We use the default mattpocock/skills triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout. See `docs/agents/domain.md`.
