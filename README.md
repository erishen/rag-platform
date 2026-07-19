# rag-platform

一个极简 RAG 学习示例项目，演示端到端的可运行 RAG 流水线：

```
用户问题
  → [词库闸门] AhoCorasick：敏感词拦截 / 问答对直答 / 同义扩展
  → [混合检索] BM25（关键词） + 向量（语义），加权融合取 Top-K
  → [生成]     OpenAI 兼容 LLM，只依据召回片段作答
```

> 📐 完整架构与设计决策详解见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 技术选型

本项目采用以下技术栈，开箱即可运行：

- **存储**：PostgreSQL + pgvector，向量检索走 `cosine_distance` SQL（非全量入内存）。
- **Embedding**：Ollama 进程外 HTTP 编码（应用进程保持轻，仅 `requests`），无 Ollama 时自动回退 sentence-transformers 进程内编码。
- **词库闸门**：AhoCorasick 实现敏感词拦截 / 问答对直答 / 同义扩展；词库缓存用 Redis（双时间戳轮询重建），Redis 缺失时回退内存。词库来源为 `data/lexicon.json`（生产 RAG 通常从数据库表拉取词库，逻辑一致）。
- **检索**：混合检索（hybrid retrieval）。对齐典型的纯向量检索方案（其只用 pgvector 向量相似度），本项目额外补一路 BM25；向量召回走 pgvector 的 `cosine_distance` SQL，两路各自 min-max 归一化后按权重融合，取 Top-K。
- **生成**：OpenAI 兼容 LLM，仅依据召回片段作答，并加「不知道就答不知道」+ 引用约束防幻觉。
- **审核流**：记录标记 active / disabled 两态。


## 目录结构

```
rag-platform/
├── app/
│   ├── main.py        # FastAPI 路由：/ingest /chat /search /lexicon/reload
│   ├── config.py      # 环境变量配置
│   ├── models.py      # SQLModel 表：Document / Chunk / QAPair
│   ├── db.py          # PostgreSQL(+pgvector) 引擎；init_db 建 vector 扩展
│   ├── embed/         # Embedding 双后端（Ollama 优先 / sentence-transformers 兜底，拆子模块）
│   │   ├── __init__.py # 薄门面：仅 re-export embed / embed_one
│   │   ├── base.py     # 后端抽象基类 EmbedBackend
│   │   ├── core.py     # 后端选择 + 维度守卫 + 公共 API（真正逻辑）
│   │   ├── ollama_backend.py   # Ollama HTTP 后端（仅 requests，主路径）
│   │   └── st_backend.py       # sentence-transformers 后端（兜底路径，进程内编码）
│   ├── bm25.py        # 从零实现的 Okapi BM25
│   ├── lexicon.py     # AhoCorasick 词库闸门（Redis 缓存 + 双时间戳轮询，可回退内存）
│   ├── retriever.py   # pgvector 向量召回 + BM25 融合 混合检索
│   ├── generator.py   # OpenAI 兼容 LLM 生成
│   ├── splitter.py    # 文本分块
│   └── schemas.py     # 请求/响应模型
├── frontend/          # Vite + Vue 前端（对话 / 入库 / 检索 三个面板）
│   ├── package.json
│   ├── vite.config.js # /api 代理到后端 :8000
│   ├── index.html
│   └── src/
│       ├── App.vue        # 顶部导航 + 后端健康探测
│       ├── api.js         # fetch 封装（/api 前缀）
│       ├── style.css
│       └── components/
│           ├── ChatPanel.vue
│           ├── IngestPanel.vue
│           └── SearchPanel.vue
├── data/
│   └── lexicon.json   # 词库样例（敏感词/同义词/问答对）
├── pyproject.toml     # uv 依赖声明（源 of truth）
├── uv.lock            # uv 锁定的依赖版本（uv sync 生成）
├── docker-compose.yml # 本地基建：PostgreSQL(+pgvector) + Redis
├── .env.example
├── Makefile           # 后端 uv + 前端 npm + 基建 compose 统一入口
```

> `requirements.txt` 保留仅作 pip 手动安装兜底；依赖以 `pyproject.toml` 为准。

## 快速开始（uv）

```bash
# 0. 起本地基建（PostgreSQL+pgvector / Redis，docker compose 一键起）
make infra-up
#   账号默认 rag:rag@localhost:5432/rag 与 .env 一致；无需 docker 时可自建服务并改 .env

# 1. 创建 .venv 并安装依赖
uv sync

# 2. 配置（必须填真实 LLM key，本项目无 mock）
cp .env.example .env
#   编辑 .env：OPENAI_API_KEY=sk-xxx，可改 OPENAI_BASE_URL 指向任意兼容网关
#   存储默认 DATABASE_URL / REDIS_URL 指向本地基建，一般无需改

# 3. 启动（用 uv run 在 .venv 里执行）
uv run uvicorn app.main:app --reload --port 8000

# 4. 建库（首次访问 /health 会自动建表并建 pgvector 扩展）
curl http://localhost:8000/health
```

> pip 用户亦可：`python -m venv .venv && pip install -r requirements.txt`
>
> 停基建：`make infra-down`（保留数据卷）；看日志：`make infra-logs`

## 前端（Vite + Vue）

提供对话 / 入库 / 检索 三个面板，开发期通过 Vite 代理同源访问后端。

### 一键启动（推荐）

`make up` 会在后台同时拉起后端（:8000）与前端（:5173），并用 PID 文件 + 日志追踪：

```bash
make install-frontend        # 首次需装前端依赖（cd frontend && npm install）
make up                      # 后台启动前后端，日志写入 logs/
#   浏览器打开 http://localhost:5173 即可
#   前端所有 /api/* 请求经代理转发到 :8000，无需手动配 CORS

make status                  # 查看前后端是否在跑
make down                    # 一键停止（按 PID 文件，并兜底按端口 / 进程名清理残留）
make restart                 # 等价于 down + up
```

### 分开前台启动（调试某一边时）

```bash
make run                     # :8000 热重载（前台，Ctrl+C 退出）
make dev                     # :5173 开发服务器（前台，Ctrl+C 退出）
```

构建静态产物（可独立托管，后端已开启 CORS）：

```bash
make build                   # 产物在 frontend/dist
make preview                 # 本地预览构建产物
```

## 试用

```bash
# 入库一篇文档
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"title":"退款说明","content":"本店商品支持 7 天无理由退款。退款将原路返回到您的支付账户。营业时间为每日 09:00 至 22:00。"}'

# 问答直答（命中词库，不走 LLM）
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"营业时间"}'

# 敏感词拦截
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"讲讲暴力内容"}'

# 走 LLM 检索作答
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question":"退款多久到账"}'

# 调试：只看检索结果
curl "http://localhost:8000/search?q=退款"
```

## 测试

测试套件位于 `tests/`，用 pytest 运行（`uv run pytest`）。共 13 个用例，分两类：

- **单元测试**（`tests/test_unit.py`，7 条）：BM25 排序、词库闸门（敏感词拦截 / 问答对直答 / 同义扩展）、文本分块、`_minmax` 归一化。**完全不依赖任何基建**，CI / 沙箱可直接跑。
- **集成测试**（`tests/test_integration.py`，6 条，标记 `@pytest.mark.integration`）：连真实 PostgreSQL+pgvector 跑完整请求链路（`/health → /ingest → /search → /chat → /lexicon/reload`），验证 `cosine_distance` 向量检索路径。无基建时**自动 skip**，不报错。

```bash
make test          # 全部：单元常跑 + 集成（有 PG 则实跑，无则 skip）
make test-unit     # 仅单元测试（CI / 无 PG 时用）
```

要点：

- 集成测试使用**独立的 `rag_test` 库**（fixture 连维护库 `postgres` 按需 `CREATE DATABASE`），不会触碰开发库 `rag`。
- 集成测试通过 `monkeypatch` 注入桩 embedding，不依赖 Ollama / sentence-transformers。
- `pyproject.toml` 已用 `filterwarnings` 过滤 Starlette 框架内部的 `httpx` 弃用提示，pytest 输出保持零警告。

## 代码质量（lint / format）

`make lint` 一把扫前后端，当前全绿、零警告：

```bash
make lint          # 后端 ruff + 前端 eslint，退出码 0
make lint-fix      # 自动修复（ruff --fix 后端 + eslint --fix 前端）
make fmt           # ruff 自动格式化（后端）
```

- **后端**：ruff 检查 `app tests`（`pyproject.toml` 中 `[tool.ruff]` 配置 `line-length=100`）。
- **前端**：ESLint 9 flat config（`frontend/eslint.config.js`）。Vue 部分使用 `flat/essential` —— 只抓真实错误（未用变量、缺 key、重复属性等），**不强制模板格式**（缩进 / 换行 / 属性顺序），避免与 IDE 格式化重复产生的无意义噪音。如需统一代码风格，应另上 Prettier（ESLint 管逻辑、Prettier 管排版，职责分离）。

## 学习路线建议

1. 先看本仓库顶部的架构数据流图与「技术选型」一节，理解整体数据流。
2. 跑通上面 4 个 curl，观察 `source` 字段区分 blocked / direct_qa / llm。
3. 改动 `data/lexicon.json` 后调 `POST /lexicon/reload` 热更新词库。
4. 进阶：BM25 接 jieba 分词；加流式输出；把词库来源从 JSON 文件换成 PG 表。
