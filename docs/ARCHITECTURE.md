# rag-platform 架构文档

> 本文档用于理解 rag-platform 的完整设计与实现细节，既是一份架构说明，
> 也作为「读懂并能在面试中 defend 这个项目」的学习材料。
> 所有描述均基于当前源码（`app/`、`frontend/`），不含推测。

---

## 1. 项目定位

rag-platform 是一个**端到端、极小依赖的 RAG 学习项目**。它从零实现了一条
完整的 RAG 流水线：文档入库（切分 + 向量化）→ 混合检索 → LLM 生成，
并附一个 AhoCorasick 词库闸门做敏感词拦截 / FAQ 直答 / 同义扩展。

设计取舍的核心特征：

- **最小依赖、from-scratch**：不依赖 LangChain / LlamaIndex 等重框架，
  RAG 的每个零件（BM25、混合检索融合、词库匹配、Embedding 双后端切换）
  都是手写或薄封装，便于理解底层原理。
- **存储用 PostgreSQL + pgvector**：向量直接存数据库 `Vector` 列，
  检索走 SQL 层的 `cosine_distance`，不把全量向量拉进内存。
- **定位是「学习 / 演示级」实现**：生产化特性（鉴权、限流、评估指标、
  HNSW 索引）有意从简，但架构是真实可跑的。

---

## 2. 架构总览

### 2.1 组件拓扑

```
                        ┌─────────────────────────────────────────┐
                        │              前端 (Vue 3 + Vite)          │
                        │  ChatPanel / IngestPanel / SearchPanel    │
                        └───────────────┬───────────────────────────┘
                                        │  HTTP  /api/*  (Vite 代理 → :8000)
                                        ▼
                        ┌─────────────────────────────────────────┐
                        │           FastAPI 应用 (app/main.py)      │
                        │  /ingest  /search  /chat  /lexicon/reload │
                        └───┬───────────┬────────────┬─────────────┘
                            │           │            │
              ┌─────────────┘           │            └──────────────┐
              ▼                         ▼                          ▼
      ┌──────────────┐         ┌──────────────┐           ┌──────────────────┐
      │  Lexicon     │         │  Retriever   │           │  Generator       │
      │  (闸门+路由) │         │  (混合检索)  │           │  (LLM 生成)      │
      │ AhoCorasick  │         │ pgvector+BM25│           │ OpenAI 兼容接口  │
      └──────┬───────┘         └──────┬───────┘           └────────┬─────────┘
             │ Redis 缓存              │                           │
             ▼                         ▼                           ▼
      ┌──────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
      │  Redis       │   │  PostgreSQL + pgvector│   │  LLM (OpenAI 兼容)   │
      │  (词库缓存)  │   │  Document / Chunk     │   │  Ollama 或云端       │
      └──────────────┘   └──────────────────────┘   └──────────────────────┘
                                    ▲
                                    │ embed 双后端 (Ollama 优先 / ST 兜底)
                                    └──────── Embedding 模块
```

### 2.2 两条核心链路

**(A) 入库链路 `/ingest`**

```
原始文档
  → split_text() 按句切分 + overlap 重叠 → 片段列表
  → embed() 双后端向量化 → (n, dim) 矩阵
  → 写入 Document 表 + 每个片段写入 Chunk 表(含 embedding 列)
```

**(B) 对话链路 `/chat`**

```
用户问题
  → [词库闸门] Lexicon.process()
        ├─ 命中 sensitive → 直接拦截，返回 "包含敏感词"
        ├─ 命中 direct_qa → 直接返回预设答案（source=direct_qa，不调 LLM）
        └─ 命中 synonyms  → 把规范词拼回 query 做同义扩展
  → [混合检索] hybrid_search(augmented_query)
        ├─ pgvector 召回 top_k*3 候选（cosine_distance）
        ├─ 候选子集上跑 BM25，两路 min-max 归一化后加权融合 → Top-K
  → [生成] generate(question, 召回片段)
        └─ LLM 仅依据召回片段作答（system prompt 限定不编造）
```

---

## 3. 模块详解

### 3.1 配置 `app/config.py`

所有配置从环境变量 / `.env` 读取，均带默认值。关键点：

| 配置项 | 默认值 | 含义 |
|------|------|------|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `LLM_MODEL` | `""` / `api.openai.com/v1` / `gpt-3.5-turbo` | LLM（OpenAI 兼容接口） |
| `EMBED_BACKEND` | `ollama` | 可选 `ollama` 或 `st`（sentence-transformers） |
| `EMBED_MODEL` | `snowflake-arctic-embed2` | 嵌入模型名（1024 维） |
| `EMBED_DIM` | `1024` | 向量维度，入库与检索必须一致 |
| `VECTOR_WEIGHT` / `BM25_WEIGHT` | `0.6` / `0.4` | 混合检索两路融合权重 |
| `TOP_K` | `4` | 最终返回片段数 |
| `DATABASE_URL` | `postgresql+psycopg://rag:rag@localhost:5432/rag` | PG + pgvector |
| `REDIS_URL` | `redis://localhost:6379/0` | 词库缓存 |
| `LEXICON_PATH` | `./data/lexicon.json` | 词库来源文件 |

> 注：LLM 要求**真实 key**（本项目不提供 mock，设计上强制真实调用）。

### 3.2 数据模型 `app/models.py` + 存储 `app/db.py`

用 SQLModel（SQLAlchemy + pydantic 合体）。三张表：

| 表 | 字段 | 说明 |
|------|------|------|
| `Document` | id, title(index), content, status(active/disabled), created_at | 原始文档 |
| `Chunk` | id, doc_id(FK), text, embedding(`Vector(EMBED_DIM)`) | 文档片段 + 向量 |
| `QAPair` | id, question, answer, status | 问答对（见下方注记） |

- `Chunk.embedding` 用 `Column(Vector(settings.embed_dim))` 包裹——这是 pgvector
  的标准做法；若不加 `Column()` 直接标 `Vector`，SQLModel 会误判类型而报错。
- `db.init_db()` 在 PostgreSQL 下先 `CREATE EXTENSION IF NOT EXISTS vector`，
  再 `create_all`。SQLite 跳扩展（本项目的向量存储目标就是 PG）。
- 向量列维度在建表后**固定**，改 `EMBED_DIM` 需重建表。

> **诚实注记**：`QAPair` 表已定义，但当前对话链路里 FAQ 直答走的是
> `Lexicon.direct_qa`（来自 `lexicon.json`），并不查 `QAPair` 表。
> 这张表是预留/未完全接线的部分——面试中如实说明即可，反而体现你清楚
> 自己代码里哪些是有意留的、哪些是冗余。

### 3.3 文本切分 `app/splitter.py`

- 用正则 `r"(?<=[。！？\n])"` 按句切分。
- 累计到约 `max_len=300` 字符成块，块尾保留 `overlap=50` 字符与下块重叠，
  缓解跨块语义割裂。
- 纯中文友好的轻量实现，无第三方依赖。

### 3.4 Embedding 双后端 `app/embed/`

结构清晰的分层：

```
__init__.py      → 薄门面，暴露 embed / embed_one
core.py          → 后端选择 + 维度守卫 + 公共 API（真正逻辑）
base.py          → EmbedBackend 抽象基类（统一 encode 接口）
ollama_backend.py→ Ollama HTTP 后端（仅 requests，主路径，轻量）
st_backend.py    → sentence-transformers 后端（重依赖，仅兜底时延迟 import）
```

行为：

1. `embed()` 优先走 Ollama（进程外 HTTP，只依赖 `requests`，启动快）；
2. Ollama 不可用 → 自动回退 sentence-transformers（进程内 PyTorch，重依赖）；
3. `st_backend` 模块被**延迟 import**（只有回退时才 `import torch`），
   保证 Ollama 主路径不被 torch 拖慢启动；
4. 两路输出都做 **L2 归一化**，便于直接算余弦；
5. `_check_dim()` 守卫：输出维度必须等于 `EMBED_DIM`，否则抛错——
   保证入库与检索在同一个向量空间。

### 3.5 词库闸门 `app/lexicon.py`

AhoCorasick 多模式匹配，一次性把三类词挂进同一台自动机，扫一遍文本即路由：

| 类别 | 来源 | 路由动作 |
|------|------|------|
| `sensitive` | `lexicon.json` 的 sensitive 列表 | 拦截，返回固定提示 |
| `synonym` | synonyms 字典（别名→规范词） | 把规范词拼回 query 做扩展 |
| `qa` | direct_qa 的 keywords | 直答，返回预设 answer（不调 LLM） |

- **Redis 缓存 + 热更新**：词库 JSON 缓存进 Redis（`rag:lexicon`）；
  `/lexicon/reload` 写「刷新信号」，后台每 10s 轮询发现信号即重建自动机。
- **内存回退**：Redis 不可用（或 `make test` 无 Redis）时自动降级为纯内存模式，
  仍可用，只是没有跨进程缓存 / 轮询重建。
- 精确匹配**永远排在向量语义检索之前**——拦截 / 直答最便宜，也最确定。

> 词库来源是 `data/lexicon.json`（样例数据），生产 RAG 通常从数据库表拉取，
> 二者逻辑一致。

### 3.6 BM25 `app/bm25.py`

从零实现的 **Okapi BM25**（无第三方依赖）：

- `score()` 对每个候选文档打分：`IDF × TF饱和项 / 长度归一化`。
- 中文 `tokenize` 当前**按字切分**（demo 够用）；生产建议换 jieba 分词。
- 这是「混合检索」额外补的一路关键词信号。

### 3.7 混合检索 `app/retriever.py`

`hybrid_search(query, session, top_k)` 是检索核心：

1. **向量召回**：用 pgvector 的 `cosine_distance` 在 SQL 层算相似度，
   取 `top_k * 3` 候选（`(1 - embedding.cosine_distance(q_vec))` 即余弦分数）。
2. **BM25 二级融合**：只在这 `top_k*3` **候选子集**上跑 BM25
   （不是全库扫描，控制开销）。
3. **归一化 + 加权融合**：向量分数与 BM25 分数各自 `min-max` 归一化到 [0,1]，
   再按 `VECTOR_WEIGHT * vec + BM25_WEIGHT * bm25` 融合。
4. 融合分数降序取 `top_k`。

> 选型细节：pgvector 的 `<->` 运算符实际是 **L2 距离**，本项目显式用
> `cosine_distance`（语义余弦），比裸 L2 更贴合文本语义。

### 3.8 生成 `app/generator.py`

- 调 OpenAI 兼容接口（`base_url` 可指向任意兼容服务）。
- `system prompt` 强约束：**只依据参考内容回答，没有就说不知道，不编造**。
- `temperature=0.1` 降低随机性，贴合知识库问答场景。

### 3.9 应用入口 `app/main.py`

- `lifespan` 启动钩子：`init_db()` 建表 + （Redis 模式）启动词库轮询任务。
- 路由：`/health`、`/ingest`、`/search`（仅检索，调试用）、`/chat`、
  `/lexicon/reload`。
- Redis 连接失败 → `_redis=None` → Lexicon 自动内存模式，主流程不受影响。
- CORS 放开 `*`（`allow_credentials=True`，开发期可接受）。

---

## 4. 关键设计决策（面试核心考点）

> 这一节是「吃透」的重点。每条都对应一个面试高频追问，建议能用自己的话复述。

### Q1：为什么做混合检索（BM25 + 向量），而不是只用向量？

- **向量检索**擅长语义匹配（"怎么退款" ↔ "退钱流程"），但**关键词精确匹配弱**
  （专有名词、型号、同形异义容易 miss）。
- **BM25** 擅长关键词精确命中，补齐向量短板。
- 两者融合是生产 RAG 的常规做法，提升召回质量与鲁棒性。

### Q2：为什么 BM25 只在候选子集上算，而不是全库？

- 向量召回先粗筛出 top_k*3 高质量候选，BM25 只在这小集合上打分；
- 若对全库每个 Chunk 跑 BM25，候选多时开销大，且低质候选的分数无助于最终结果；
- 这是「向量粗排 + 关键词精排」的两阶段思路，兼顾质量与成本。

### Q3：为什么两路分数要做 min-max 归一化再融合？

- 向量分数（余弦，约 [0,1]）与 BM25 分数（可正可负、量纲不同）**不可直接相加**；
- min-max 把各自的分布拉到 [0,1] 同量纲，再按权重融合才有意义；
- 否则 BM25 绝对值大就会淹没向量信号（或反之）。

### Q4：为什么用 pgvector 的 cosine_distance，而不是把向量拉进内存算？

- 向量存数据库 `Vector` 列，检索在 SQL 层完成，**不需要把全量向量加载到应用内存**；
- 数据量大时（百万级）内存放不下，SQL 层还能建 HNSW / ivfflat 向量索引加速；
- 也是「存储与计算下沉到数据库」的工程化取向。

### Q5：AhoCorasick 词库闸门解决了什么问题？为什么排在检索之前？

- 用一台自动机 O(n) 扫描文本、一次性识别敏感词 / 同义词 / QA 关键词；
- 拦截和直答是**最便宜、最确定**的动作，应前置短路：
  - 含敏感词直接挡掉（合规硬杠，不依赖 LLM）；
  - FAQ 高频问题直接命中预设答案（省一次 LLM 调用、延迟更低、答案更稳定）。

### Q6：Embedding 为什么要做 Ollama + sentence-transformers 双后端？

- Ollama 进程外、轻量（只 requests）、易本地部署，适合主路径；
- sentence-transformers 进程内、质量高但有 torch 重依赖，作为兜底；
- 延迟 import torch 保证主路径不被重依赖拖慢；维度守卫保证两路向量空间一致。

---

## 5. API 清单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（llm_configured / redis 状态） |
| POST | `/ingest` | 文档入库：`{title, content}` → 切分+向量化写入 |
| GET | `/search?q=&top_k=` | 仅检索（不调 LLM），调试用 |
| POST | `/chat` | 对话：`{question}` → 闸门+检索+生成 |
| POST | `/lexicon/reload` | 热重载词库文件（写 Redis 刷新信号） |

`ChatResponse.source` 取值：`blocked` / `direct_qa` / `llm`。

---

## 6. 面试防御清单（高频题 + 标准答法）

> 照着过一遍，能讲清这些即可把 rag-platform 从「大概知道」变成「能扛问」。

1. **画一遍 /chat 的完整链路**
   → 词库闸门（敏感/同义/直答）→ 同义扩展 query → 混合检索（向量召回 top_k*3
   + BM25 子集打分 + min-max 融合）→ LLM 仅依片段作答。

2. **为什么混合检索？BM25 和向量的优劣各是什么？**
   → 见 §4 Q1。

3. **向量和 BM25 分数怎么融合？为什么不能粗暴相加？**
   → 见 §4 Q3（min-max 归一化到同量纲再加权）。

4. **pgvector 检索具体怎么写的？cosine_distance 是什么？**
   → SQLModel 里 `(1 - Chunk.embedding.cosine_distance(q_vec))` 排序取候选；
   cosine_distance 是 pgvector 提供的余弦距离函数；`<->` 实际是 L2，项目特意用余弦。

5. **AhoCorasick 闸门三个类别分别干什么？为什么敏感词拦截不用 LLM？**
   → 见 §4 Q5（确定性 + 成本 + 合规硬杠）。

6. **词库热更新怎么实现的？Redis 挂了怎么办？**
   → `/lexicon/reload` 写刷新信号，后台 10s 轮询重建自动机；Redis 不可用自动降级内存模式。

7. **Embedding 双后端如何切换？torch 为什么不影响启动速度？**
   → Ollama 优先、ST 兜底；st_backend 延迟 import，主路径不加载 torch。

8. **如果把这个项目做成生产级，你会改什么？**
   → 中文 BM25 换 jieba；百万级建 HNSW 向量索引；加鉴权 / 限流 / 评估指标；
   接流式输出；词库来源从 JSON 文件迁到 PG 表（逻辑一致）；QAPair 表真正接线。

9. **这个项目的定位是什么？**
   → 个人 RAG 学习 / 开源 demo，从零实现、最小依赖，演示端到端 RAG 流水线；
   非生产系统（诚实表述）。

---

## 7. 运行与扩展

### 本地运行（依赖 Docker 起 PG + Redis）

```bash
docker compose up -d          # 启动 postgres(pgvector) + redis
cp .env.example .env          # 填入真实 OPENAI_API_KEY（本项目要求真实 LLM）
uv run fastapi dev app/main.py   # 或 make run
# 前端
cd frontend && npm install && npm run dev
```

### 测试与代码质量

```bash
make test        # pytest（单元 + 集成，集成测试用独立 rag_test 库）
make test-unit   # 仅单元测试
make lint        # ruff(后端) + eslint(前端)
```

### 常见扩展方向

- 中文 BM25 接 jieba 分词；
- 向量库建 HNSW / ivfflat 索引应对百万级；
- FAQ 直答改为向量近邻短路（处理"换种说法问"）；
- 词库来源从 JSON 文件换成 PG 表；
- 加流式输出、评估指标、鉴权。

---

## 附：目录结构

```
rag-platform/
├── app/
│   ├── main.py          # FastAPI 入口 + 路由 + lifespan 轮询
│   ├── config.py        # 全局配置
│   ├── db.py            # PG 引擎 + 建表 + pgvector 扩展
│   ├── models.py        # Document / Chunk / QAPair 三张表
│   ├── schemas.py       # 请求/响应 pydantic 模型
│   ├── splitter.py      # 按句切分 + overlap
│   ├── lexicon.py       # AhoCorasick 词库闸门 + Redis 缓存
│   ├── bm25.py          # 从零实现 Okapi BM25
│   ├── retriever.py     # 混合检索（pgvector + BM25 融合）
│   ├── generator.py     # LLM 生成（OpenAI 兼容）
│   └── embed/           # 双后端 Embedding（ollama 优先 / st 兜底）
├── data/
│   └── lexicon.json     # 词库样例数据（sensitive/synonyms/direct_qa）
├── frontend/            # Vue3 + Vite 三面板 demo
├── tests/               # pytest 单元 + 集成
├── docker-compose.yml   # postgres(pgvector) + redis
├── README.md
└── LICENSE              # MIT
```
