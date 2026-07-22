COMPOSE_FILE := docker-compose.dev.yml
COMPOSE      := docker compose -f $(COMPOSE_FILE)

BACKEND_GPU_BASE_IMAGE ?= kakj/xscz-backend-base:gpu-dev
FRONTEND_BASE_IMAGE    ?= kakj/xscz-frontend-base:dev
TAIL                   ?= 200
SERVICE                ?=
PYTEST_ARGS            ?=

export BACKEND_GPU_BASE_IMAGE
export FRONTEND_BASE_IMAGE

.DEFAULT_GOAL := help

.PHONY: help init setup config base-build base-build-backend base-build-frontend \
	up rebuild down restart ps logs shell \
	db-upgrade db-current db-history db-revision \
	test test-backend test-frontend lint lint-backend lint-frontend

help: ## 显示可用命令
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Docker 开发环境 ────────────────────────────────────────────────────────
init: ## 从 .env.example 创建缺失的 .env
	@if [ -f .env ]; then \
		echo ".env 已存在"; \
	else \
		cp .env.example .env; \
		echo "已创建 .env，请按需修改"; \
	fi

setup: init base-build up ## 首次构建基础镜像并启动开发环境

config: ## 校验并解析 Docker Compose 开发配置
	$(COMPOSE) config --quiet

base-build: base-build-backend base-build-frontend ## 构建前后端开发基础镜像

base-build-backend: ## 构建后端 GPU 开发基础镜像
	docker buildx build --load -f docker/backend/Dockerfile.gpu.base -t $(BACKEND_GPU_BASE_IMAGE) .

base-build-frontend: ## 构建前端开发基础镜像
	docker buildx build --load -f docker/frontend/Dockerfile.base -t $(FRONTEND_BASE_IMAGE) .

up: init ## 构建并启动开发环境
	$(COMPOSE) up -d --build

rebuild: init ## 强制重建并重新创建开发容器
	$(COMPOSE) up -d --build --force-recreate

down: ## 停止并移除开发容器（保留数据卷）
	$(COMPOSE) down --remove-orphans

restart: ## 重启开发容器
	$(COMPOSE) restart

ps: ## 查看开发容器状态
	$(COMPOSE) ps

logs: ## 跟踪日志；可用 SERVICE=backend、TAIL=500 过滤
	$(COMPOSE) logs -f --tail=$(TAIL) $(SERVICE)

shell: ## 进入后端开发容器
	$(COMPOSE) exec backend bash

# ── 数据库 ────────────────────────────────────────────────────────────────
db-upgrade: ## 应用全部数据库迁移
	$(COMPOSE) exec backend alembic upgrade heads

db-current: ## 查看当前数据库迁移版本
	$(COMPOSE) exec backend alembic current

db-history: ## 查看数据库迁移历史
	$(COMPOSE) exec backend alembic history --verbose

db-revision: ## 生成迁移：make db-revision MSG="add users table"
	@test -n "$(MSG)" || (echo '缺少 MSG，例如：make db-revision MSG="add users table"' && exit 1)
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(MSG)"

# ── 质量检查（在开发容器内运行）──────────────────────────────────────────
test: test-backend test-frontend ## 运行前后端测试

test-backend: ## 运行后端测试；可传 PYTEST_ARGS="tests/unit -q"
	$(COMPOSE) exec -T backend pytest $(PYTEST_ARGS)

test-frontend: ## 运行前端单元测试
	$(COMPOSE) exec -T frontend npm run test

lint: lint-backend lint-frontend ## 运行前后端 lint

lint-backend: ## 运行后端 Ruff 检查
	$(COMPOSE) exec -T backend ruff check app tests

lint-frontend: ## 运行前端 ESLint 检查
	$(COMPOSE) exec -T frontend npm run lint
