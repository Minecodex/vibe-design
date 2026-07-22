# Docker 部署指南

本文档是像素重组 Docker 部署的事实来源，覆盖固定版本镜像、必填配置、CPU/GPU/ARM64 启动、Windows PowerShell、升级和排障。

> [!IMPORTANT]
> 生产部署必须显式指定镜像版本。不要直接使用 Compose 文件中的 `latest` 回退值，也不要使用浮动标签替代本文档中经过验证的版本。

## 已验证镜像版本

当前验证版本：`20260722`

| 组件 | 架构 | 镜像 |
| --- | --- | --- |
| 前端 | amd64 / arm64 | `kakj/xscz-frontend-app:20260722` |
| CPU 后端 | amd64 | `kakj/xscz-backend-app:cpu-20260722` |
| GPU 后端 | amd64 | `kakj/xscz-backend-app:gpu-20260722` |
| ARM64 后端 | arm64 | `kakj/xscz-backend-app:arm64-20260722` |

## 部署要求

- Docker Engine
- Docker Compose v2.24 或更高版本
- 当前默认运行参数按 8 核 / 16 线程、32 GB 内存配置
- GPU 配置建议约 16 GB 显存
- 可公网读取对象的 TOS 兼容 Bucket
- 可用的模型提供商账号

Compose 会启动以下服务：

- MySQL 8.4：业务事实与持久化任务
- Redis 7.4：多进程协调、唤醒、去重和发布订阅
- FastAPI Backend：API 与 SSE
- Agent Worker：Agent Run 和工具执行
- Background Worker：媒体生成、轮询和后台任务
- Nginx + React Frontend：Web 应用与 API 代理

## 1. 准备仓库与环境变量

```bash
git clone https://github.com/kakj-go/ai-code.git
cd ai-code
cp .env.example .env
```

编辑 `.env`，不要直接使用示例中的开发密码。

### 必填安全配置

```dotenv
APP_ENV=production
DEBUG=false
SECRET_KEY=<足够长的随机字符串>
MYSQL_PASSWORD=<数据库用户密码>
MYSQL_ROOT_PASSWORD=<数据库-root-密码>
```

如通过自定义域名访问，还需要调整：

```dotenv
APP_API_BASE_URL=https://your-domain.example
ALLOWED_ORIGINS=https://your-domain.example
```

### 必填对象存储配置

本地参考图在提交给远程图片或视频模型前，会先上传到对象存储。正常部署必须提供有效的 TOS 凭证。

```dotenv
# 必填，不能留空
TOS_AK=<你的-TOS-Access-Key>
TOS_SK=<你的-TOS-Secret-Key>

# 必须与实际 Bucket 一致
TOS_ENDPOINT=tos-cn-guangzhou.volces.com
TOS_REGION=cn-guangzhou
TOS_BUCKET_NAME=<你的公网-Bucket>

# 可选；使用 CDN 或自定义公网域名时设置
TOS_PUBLIC_BASE_URL=
TOS_OBJECT_PREFIX=generation-refs/
```

| 配置 | 是否必填 | 说明 |
| --- | --- | --- |
| `TOS_AK` | **是** | TOS Access Key；必须由部署者填写 |
| `TOS_SK` | **是** | TOS Secret Key；必须由部署者填写 |
| `TOS_ENDPOINT` | 是 | Bucket 所在 Endpoint；示例值仅适用于对应区域 |
| `TOS_REGION` | 是 | Bucket 所在 Region |
| `TOS_BUCKET_NAME` | 是 | 能够通过公网 URL 读取对象的 Bucket |
| `TOS_PUBLIC_BASE_URL` | 否 | CDN 或自定义公网访问前缀 |
| `TOS_OBJECT_PREFIX` | 否 | 参考图对象 Key 前缀 |

> [!WARNING]
> `TOS_AK` 或 `TOS_SK` 留空会导致本地参考图无法上传，进而使参考图、图生图及依赖本地媒体的生成流程失败。不要将真实凭证提交到 Git、日志、Issue 或截图中。

## 2. 选择部署配置

| 目标环境 | Compose 文件 | 后端镜像变量 |
| --- | --- | --- |
| CPU / x86_64 | `docker-compose.cpu.yml` | `BACKEND_CPU_APP_IMAGE` |
| NVIDIA GPU / x86_64 | `docker-compose.gpu.yml` | `BACKEND_GPU_APP_IMAGE` |
| ARM64 | `docker-compose.arm.yml` | `BACKEND_ARM64_APP_IMAGE` |

所有配置都必须同时指定 `FRONTEND_APP_IMAGE=kakj/xscz-frontend-app:20260722`。

## 3. Linux / macOS 部署

### CPU / x86_64

```bash
export COMPOSE_PROJECT_NAME=xscz
export BACKEND_CPU_APP_IMAGE=kakj/xscz-backend-app:cpu-20260722
export FRONTEND_APP_IMAGE=kakj/xscz-frontend-app:20260722

docker compose -f docker-compose.cpu.yml pull
docker compose -f docker-compose.cpu.yml up -d mysql redis
docker compose -f docker-compose.cpu.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.cpu.yml up -d
```

### GPU / x86_64

```bash
export COMPOSE_PROJECT_NAME=xscz
export BACKEND_GPU_APP_IMAGE=kakj/xscz-backend-app:gpu-20260722
export FRONTEND_APP_IMAGE=kakj/xscz-frontend-app:20260722

docker compose -f docker-compose.gpu.yml pull
docker compose -f docker-compose.gpu.yml up -d mysql redis
docker compose -f docker-compose.gpu.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.gpu.yml up -d
```

### ARM64

```bash
export COMPOSE_PROJECT_NAME=xscz
export BACKEND_ARM64_APP_IMAGE=kakj/xscz-backend-app:arm64-20260722
export FRONTEND_APP_IMAGE=kakj/xscz-frontend-app:20260722

docker compose -f docker-compose.arm.yml pull
docker compose -f docker-compose.arm.yml up -d mysql redis
docker compose -f docker-compose.arm.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.arm.yml up -d
```

## 4. Windows PowerShell 部署

以下分别给出 GPU、CPU 和 ARM64 的完整命令。

```powershell
$env:COMPOSE_PROJECT_NAME = "xscz"
$env:BACKEND_GPU_APP_IMAGE = "kakj/xscz-backend-app:gpu-20260722"
$env:FRONTEND_APP_IMAGE = "kakj/xscz-frontend-app:20260722"

docker compose -f docker-compose.gpu.yml pull
docker compose -f docker-compose.gpu.yml up -d mysql redis
docker compose -f docker-compose.gpu.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.gpu.yml up -d
```

CPU / x86_64：

```powershell
$env:COMPOSE_PROJECT_NAME = "xscz"
$env:BACKEND_CPU_APP_IMAGE = "kakj/xscz-backend-app:cpu-20260722"
$env:FRONTEND_APP_IMAGE = "kakj/xscz-frontend-app:20260722"

docker compose -f docker-compose.cpu.yml pull
docker compose -f docker-compose.cpu.yml up -d mysql redis
docker compose -f docker-compose.cpu.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.cpu.yml up -d
```

ARM64：

```powershell
$env:COMPOSE_PROJECT_NAME = "xscz"
$env:BACKEND_ARM64_APP_IMAGE = "kakj/xscz-backend-app:arm64-20260722"
$env:FRONTEND_APP_IMAGE = "kakj/xscz-frontend-app:20260722"

docker compose -f docker-compose.arm.yml pull
docker compose -f docker-compose.arm.yml up -d mysql redis
docker compose -f docker-compose.arm.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.arm.yml up -d
```

## 5. 验证部署

以 CPU 配置为例：

```bash
docker compose -f docker-compose.cpu.yml ps
docker compose -f docker-compose.cpu.yml logs --tail=100 backend agent-worker background-worker
curl http://127.0.0.1:8000/health
```

服务地址：

- Web 应用：<http://localhost:5173>
- API 文档：<http://127.0.0.1:8000/api/v1/docs>
- API 健康检查：<http://127.0.0.1:8000/health>

所有容器应处于 `running` 状态，MySQL 与 Redis 应通过健康检查。

## 6. 使用默认管理员登录

数据库迁移会自动创建默认管理员账号：

| 字段 | 默认值 |
| --- | --- |
| 用户名 | `admin` |
| 邮箱 | `admin@admin.com` |
| 密码 | `123456` |

部署完成后：

1. 打开 <http://localhost:5173>。
2. 使用用户名 `admin` 或邮箱 `admin@admin.com` 登录。
3. 输入默认密码 `123456`。
4. **首次登录后立即修改默认密码。**
5. 在应用设置中配置管理员的 APIMart Key。
6. 根据实际需要创建普通用户账号。

> [!WARNING]
> 默认管理员密码是公开信息。任何共享、测试或生产部署都不能长期保留 `123456`；完成首次登录后应立即更换，并避免在日志、截图或工单中记录新密码。

## 常用运维命令

以下命令以 CPU 配置为例；GPU/ARM64 替换 Compose 文件即可。

```bash
# 查看状态
docker compose -f docker-compose.cpu.yml ps

# 持续查看日志
docker compose -f docker-compose.cpu.yml logs -f

# 只查看 Worker 日志
docker compose -f docker-compose.cpu.yml logs -f agent-worker background-worker

# 停止服务但保留数据卷
docker compose -f docker-compose.cpu.yml down

# 查看数据库迁移版本
docker compose -f docker-compose.cpu.yml exec backend alembic current
```

不要在需要保留数据时使用 `down -v`。

## 固定版本升级

升级前先确定新的前端和后端镜像标签，并备份 MySQL 数据与上传目录。不要直接切换到 `latest`。

```bash
export BACKEND_CPU_APP_IMAGE=<新的固定 CPU 后端镜像>
export FRONTEND_APP_IMAGE=<新的固定前端镜像>

docker compose -f docker-compose.cpu.yml pull
docker compose -f docker-compose.cpu.yml up -d mysql redis
docker compose -f docker-compose.cpu.yml run --rm backend alembic upgrade heads
docker compose -f docker-compose.cpu.yml up -d
docker compose -f docker-compose.cpu.yml ps
```

如需回滚应用版本，恢复原固定镜像标签并重新执行 `up -d`。数据库是否可回滚取决于对应 Alembic Migration，执行 `alembic downgrade` 前必须检查迁移内容并备份数据库。

## 从源码构建镜像

普通部署优先使用上方固定版本镜像。仅在开发或发布自定义版本时构建镜像。

### 基础镜像

```bash
docker buildx build --platform linux/amd64 -f docker/backend/Dockerfile.cpu.base -t kakj/xscz-backend-base:cpu-20260721 --push .

docker buildx build --platform linux/amd64  -f docker/backend/Dockerfile.gpu.base  -t kakj/xscz-backend-base:gpu-20260721 --push .

docker buildx build --platform linux/arm64  -f docker/backend/Dockerfile.arm64.base  -t kakj/xscz-backend-base:arm64-20260721 --push .

docker buildx build --platform linux/amd64,linux/arm64  -f docker/frontend/Dockerfile.base  -t kakj/xscz-frontend-base:20260721 --push .
```

### 应用镜像

```bash
docker buildx build --platform linux/amd64  -f docker/backend/Dockerfile.cpu.app  --build-arg BACKEND_BASE_IMAGE=kakj/xscz-backend-base:cpu-20260721  -t kakj/xscz-backend-app:cpu-20260722 --push .

docker buildx build --platform linux/amd64  -f docker/backend/Dockerfile.gpu.app  --build-arg BACKEND_BASE_IMAGE=kakj/xscz-backend-base:gpu-20260721  -t kakj/xscz-backend-app:gpu-20260722 --push .

docker buildx build --platform linux/arm64  -f docker/backend/Dockerfile.arm64.app  --build-arg BACKEND_BASE_IMAGE=kakj/xscz-backend-base:arm64-20260721  -t kakj/xscz-backend-app:arm64-20260722 --push .

docker buildx build --platform linux/amd64,linux/arm64  -f docker/frontend/Dockerfile.app  --build-arg FRONTEND_BASE_IMAGE=kakj/xscz-frontend-base:20260721  -t kakj/xscz-frontend-app:20260722 --push .
```

发布新版本时，应为所有应用镜像使用同一个新的不可变版本号，并同步更新本部署文档。

## 开发环境

开发配置使用源码目录挂载和开发镜像：

```bash
cp .env.example .env
# 填写 TOS_AK、TOS_SK 及其他必填配置

docker buildx build -f docker/backend/Dockerfile.gpu.base \
  -t kakj/xscz-backend-base:gpu-dev --load .

docker buildx build -f docker/frontend/Dockerfile.base \
  -t kakj/xscz-frontend-base:dev --load .

$env:BACKEND_GPU_BASE_IMAGE = "kakj/xscz-backend-base:gpu-dev"
$env:FRONTEND_BASE_IMAGE = "kakj/xscz-frontend-base:dev"
docker compose -f docker-compose.dev.yml up -d --build

docker compose -f docker-compose.dev.yml exec backend alembic upgrade heads
```

停止开发环境：

```bash
docker compose -f docker-compose.dev.yml down
```

## 故障排查

### 参考图生成失败

检查以下内容：

1. `.env` 中 `TOS_AK` 和 `TOS_SK` 是否已填写且未包含多余引号或空格。
2. `TOS_ENDPOINT`、`TOS_REGION` 与 `TOS_BUCKET_NAME` 是否属于同一个 Bucket。
3. 凭证是否有向目标前缀执行 `PutObject` 的权限。
4. 上传后的对象是否能通过最终公网 URL 被模型提供商访问。
5. 使用自定义域名时，`TOS_PUBLIC_BASE_URL` 是否包含正确协议和域名。

### Backend 或 Worker 无法启动

```bash
docker compose -f docker-compose.cpu.yml logs --tail=200 backend
docker compose -f docker-compose.cpu.yml logs --tail=200 agent-worker
docker compose -f docker-compose.cpu.yml logs --tail=200 background-worker
```

重点检查 MySQL/Redis 健康状态、数据库密码是否一致、Migration 是否已执行，以及 `.env` 是否存在。

### 前端无法访问 API

检查 `APP_API_BASE_URL`、`ALLOWED_ORIGINS` 和反向代理配置。使用域名部署时，这两个变量不能继续保留为仅适用于本机的默认地址。

## 安全提醒

- 不要提交 `.env`、TOS 凭证、模型 Key、Cookie、Token、许可证材料或私钥。
- Compose 当前会向宿主机发布 MySQL `3306` 与 Redis `6379`，公网主机必须使用防火墙或修改监听地址。
- Backend 与 Worker 为 Bubblewrap 沙箱授予了 `SYS_ADMIN` 并放宽 seccomp/AppArmor，请根据实际威胁模型进行加固。
- 公网部署应使用 TLS，并通过反向代理限制管理接口和数据库访问。



## trace
python -m runtime.export_harness_trace --user-id 1 --conversation-id 1782458883895_1045ff --profile full
