# PR 与 CI 合并规则

默认主分支为 `main`。必须通过 PR、固定 GitHub Actions `CI`、同步主分支并解决审查讨论；失败、取消、意外跳过都不能通过。禁止强推、删除和管理员绕过。

| 阶段 | 实际范围 |
| --- | --- |
| 普通 PR / main push | 后端 pytest、前端 lint/Vitest/类型/生产构建；真实 SQLite/Redis 后端上的 Chromium 登录、亮暗主题和项目持久化 |
| v* / 手动发布候选 | 同一源码 CI；CPU amd64、GPU 镜像 amd64、ARM64 的原生构建；真实 MySQL/Redis 迁移、双 worker 与生产前端 |
| 发布浏览器 | Chromium/Firefox/WebKit 的登录/项目持久化，以及实际画布加载、编辑、自动保存、重载和过期版本拒绝 |
| 独立环境 | 真实模型、外部提供商、完整媒体生成链路及物理 GPU/CUDA 质量与吞吐 |

浏览器配置使用 `VIBE_E2E_PROFILE=pr|release`，未知值直接失败。发布使用生产前端和实际候选镜像，六项单浏览器核心/画布断言在全部三个引擎与三个原生部署 profile 上执行，不以模拟前端状态替代持久化。测试使用独立数据库和测试账户，没有生产配置、真实提供商凭据或外部发布操作。

发布只由版本标签或手动候选触发；PR 的 `ci:release` 标签不再让每次提交重复执行完整发布。固定 `Release CI` 要求源码和全部部署 profile 成功，只保存内部制品，不推送镜像或公开版本。普通托管 GPU 镜像运行不证明物理 CUDA 测试通过。

历史 `auth.spec.ts` / `users.spec.ts` 等使用退役的注册与 AntD 流程，不作为当前产品的发布验收；当前 UI 与后端协议通过 `core.spec.ts` / `release.spec.ts` 验证，其他场景应按当前业务合同独立维护。没有定时任务、专用 Runner 或额外 Actions Secret/Environment 前置条件。
