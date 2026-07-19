# rag-platform —— 极简 RAG 学习项目 Makefile
# 依赖管理使用 uv，所有命令通过 `uv run` 在 .venv 中执行。
#
# 常用：
#   make install            # 后端：同步依赖到 .venv（uv sync）
#   make install-frontend   # 前端：安装 npm 依赖（frontend/node_modules）
#   make run                # 后端：本地热重载启动 API（:8000）
#   make dev                # 前端：启动 Vite 开发服务器（:5173，/api 代理到 :8000）
#   make build              # 前端：构建静态产物到 frontend/dist
#   make preview            # 前端：本地预览构建产物
#   make test               # 运行测试（pytest：单元常跑，集成无基建自动 skip）
#   make infra-up           # 启动本地基建（Postgres+pgvector / Redis，docker compose）
#   make infra-down         # 停止本地基建
#   make clean              # 清缓存

PYTHON := uv run python
UV := uv
NPM := npm

# 前后端一体（后台运行）相关路径：PID 文件 + 日志
PID_DIR := .pids
LOG_DIR := logs
BACKEND_PID := $(PID_DIR)/backend.pid
FRONTEND_PID := $(PID_DIR)/frontend.pid
BACKEND_LOG := $(LOG_DIR)/backend.log
FRONTEND_LOG := $(LOG_DIR)/frontend.log

.PHONY: help install lock run serve test lint lint-fix fmt health ingest chat shell clean \
        install-frontend dev build preview up start down stop restart status \
        infra-up infra-down infra-logs lint-frontend lint-frontend-fix

help:  ## 打印可用目标
	@echo "可用目标："
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## 同步依赖到 .venv（uv sync）
	$(UV) sync

lock:  ## 重新解析并锁定依赖（uv lock）
	$(UV) lock

run serve:  ## 启动 API（热重载，:8000）
	$(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:  ## 运行全部测试（单元测试常跑；集成测试无基建自动 skip）
	$(UV) run pytest

test-unit:  ## 只跑无需基建的单元测试（CI / 无 PG 时用）
	$(UV) run pytest -m "not integration"

lint:  ## 静态检查（ruff 后端 + eslint 前端）
	$(UV) run ruff check app tests
	cd frontend && $(NPM) run lint

lint-fix:  ## 自动修复（ruff --fix 后端 + eslint --fix 前端）
	$(UV) run ruff check --fix app tests
	cd frontend && $(NPM) run lint:fix

fmt:  ## ruff 自动格式化（后端）
	$(UV) run ruff format app tests

lint-frontend:  ## 仅前端 eslint 检查
	cd frontend && $(NPM) run lint

lint-frontend-fix:  ## 仅前端 eslint 自动修复
	cd frontend && $(NPM) run lint:fix

health:  ## 探活 /health
	@curl -s http://127.0.0.1:8000/health || echo "服务未启动"

ingest:  ## 示例：POST 一篇文档入库（改 TITLE/CONTENT 即可）
	@curl -s -X POST http://127.0.0.1:8000/ingest \
		-H 'Content-Type: application/json' \
		-d '{"title":"示例文档","content":"这是一段用于检索的中文文本。"}'

chat:  ## 示例：向 /chat 提问
	@curl -s -X POST http://127.0.0.1:8000/chat \
		-H 'Content-Type: application/json' \
		-d '{"question":"这是一段用于检索的中文文本吗？"}'

shell:  ## 进入项目 Python REPL
	$(UV) run python

# ---------- 前端（Vite + Vue）----------
install-frontend:  ## 安装前端依赖（frontend/node_modules）
	cd frontend && $(NPM) install

dev:  ## 启动前端开发服务器（:5173，/api 代理到后端 :8000）
	cd frontend && $(NPM) run dev

build:  ## 构建前端静态产物到 frontend/dist
	cd frontend && $(NPM) run build

preview:  ## 本地预览前端构建产物
	cd frontend && $(NPM) run preview

# ---------- 前后端一体（后台运行 + PID 追踪）----------
up start:  ## 一键后台启动前后端（:8000 + :5173），日志见 logs/
	@mkdir -p $(PID_DIR) $(LOG_DIR)
	@if [ -f $(BACKEND_PID) ] && kill -0 $$(cat $(BACKEND_PID)) 2>/dev/null; then \
		echo "后端已在运行 (pid $$(cat $(BACKEND_PID)))"; \
	else \
		nohup $(UV) run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > $(BACKEND_LOG) 2>&1 & \
		echo $$! > $(BACKEND_PID); \
		echo "后端已启动 (pid $$(cat $(BACKEND_PID))) -> $(BACKEND_LOG)"; \
	fi
	@if [ -f $(FRONTEND_PID) ] && kill -0 $$(cat $(FRONTEND_PID)) 2>/dev/null; then \
		echo "前端已在运行 (pid $$(cat $(FRONTEND_PID)))"; \
	else \
		nohup $(NPM) --prefix frontend run dev > $(FRONTEND_LOG) 2>&1 & \
		echo $$! > $(FRONTEND_PID); \
		echo "前端已启动 (pid $$(cat $(FRONTEND_PID))) -> $(FRONTEND_LOG)"; \
	fi
	@sleep 1
	@echo "========================================================="
	@echo " 前端: http://localhost:5173"
	@echo " 后端: http://localhost:8000"
	@echo " 日志: $(FRONTEND_LOG) | $(BACKEND_LOG)"
	@echo " 停止: make down"
	@echo "========================================================="

down stop:  ## 停止前后端（先按 PID 文件，再兜底按端口 / 进程名清理）
	@if [ -f $(BACKEND_PID) ]; then \
		kill $$(cat $(BACKEND_PID)) 2>/dev/null && echo "已停止后端 (pid $$(cat $(BACKEND_PID)))"; \
		rm -f $(BACKEND_PID); \
	fi
	@if [ -f $(FRONTEND_PID) ]; then \
		kill $$(cat $(FRONTEND_PID)) 2>/dev/null && echo "已停止前端 (pid $$(cat $(FRONTEND_PID)))"; \
		rm -f $(FRONTEND_PID); \
	fi
	@for p in 8000 5173; do \
		pid=$$(lsof -ti tcp:$$p 2>/dev/null); \
		if [ -n "$$pid" ]; then kill $$pid 2>/dev/null && echo "已清理端口 $$p 上的残留进程 ($$pid)"; fi; \
	done
	@pkill -f "uvicorn app.main:app" 2>/dev/null && echo "已清理 uvicorn 残留" || true
	@pkill -f "vite" 2>/dev/null && echo "已清理 vite 残留" || true

restart:  ## 重启前后端（down 后 up）
	@$(MAKE) down
	@$(MAKE) up

status:  ## 查看前后端运行状态
	@echo "后端 :8000 -> $$(lsof -ti tcp:8000 2>/dev/null | head -1 | sed 's/^/pid /' || echo '未运行')"
	@echo "前端 :5173 -> $$(lsof -ti tcp:5173 2>/dev/null | head -1 | sed 's/^/pid /' || echo '未运行')"

# ---------- 本地基建（PostgreSQL+pgvector / Redis，docker compose）----------
infra-up:  ## 启动本地基建（Postgres+pgvector / Redis）
	docker compose up -d
	@echo "基础设施已启动：Postgres :5432 / Redis :6379"

infra-down:  ## 停止并移除本地基建容器（保留数据卷）
	docker compose down

infra-logs:  ## 查看基建日志
	docker compose logs -f

clean:  ## 清理 Python 缓存与本地数据库（含测试库）
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -f data/rag.db data/test.db
	rm -rf $(LOG_DIR) $(PID_DIR) .pytest_cache tests/.pytest_cache
	@echo "已清理 __pycache__ / *.pyc / data/rag.db / data/test.db / $(LOG_DIR) / $(PID_DIR) / .pytest_cache"
