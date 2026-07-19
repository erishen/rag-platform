"""FastAPI 应用入口。

请求链路（对应典型的 /chat 接口）：
  用户问题
    → [词库闸门] 敏感词拦截 / 问答对直答 / 同义扩展
    → [混合检索] pgvector 向量召回 + BM25 融合，召回 Top-K 片段
    → [生成]   LLM 仅依据召回片段作答

存储层：PostgreSQL + pgvector 存向量，Redis 缓存词库（见 app/lexicon.py）。
"""
import asyncio
from contextlib import asynccontextmanager

import redis as redis_lib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import schemas
from app.config import settings
from app.db import get_session, init_db
from app.embed import embed
from app.generator import generate
from app.lexicon import Lexicon
from app.models import Chunk, Document
from app.retriever import hybrid_search
from app.splitter import split_text


# 词库轮询（仅 Redis 模式需要，生命周期由 lifespan 管理）
async def _poll_lexicon() -> None:
    """每 10s 检查 Redis 词库更新信号，必要时重建 AhoCorasick。"""
    while True:
        lexicon.check_update()
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：建表 + （Redis 模式下）启动词库轮询
    init_db()
    poller = None
    if _redis is not None:
        poller = asyncio.create_task(_poll_lexicon())
    yield
    # 关闭：取消轮询任务
    if poller is not None:
        poller.cancel()


app = FastAPI(title="rag-platform", version="0.1.0", lifespan=lifespan)

# 允许跨域：开发期 Vite 代理同源即够用；若把构建产物（frontend/dist）
# 托管到别的端口/域名，需放开 CORS 才能访问 :8000。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis 客户端：连接失败则回退内存词库模式（不影响主流程）
try:
    _redis = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
    _redis.ping()
except Exception:
    _redis = None
    print("[warn] Redis 不可用，词库回退为内存模式（无跨进程缓存 / 轮询重建）")

lexicon = Lexicon(settings.lexicon_path, _redis)

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": bool(settings.openai_api_key),
        "redis": _redis is not None,
    }


# ---------- 入库 ----------
@app.post("/ingest", summary="文档入库：切分 + 向量化")
def ingest(req: schemas.IngestRequest) -> dict:
    with get_session() as s:
        doc = Document(title=req.title, content=req.content)
        s.add(doc)
        s.commit()
        s.refresh(doc)
        doc_id = doc.id  # 在 session 关闭前取出，避免 detached 后访问触发 lazy reload

        pieces = split_text(req.content)
        vecs = embed(pieces)  # np.ndarray (n, dim)
        for text, vec in zip(pieces, vecs):
            chunk = Chunk(
                doc_id=doc_id,
                text=text,
                embedding=vec.tolist(),  # pgvector 接受 list[float]
            )
            s.add(chunk)
        s.commit()
    return {"doc_id": doc_id, "chunks": len(pieces)}


# ---------- 检索（调试用） ----------
@app.get("/search", summary="仅检索，不调用 LLM")
def search(q: str, top_k: int | None = None) -> list[schemas.SearchResultItem]:
    with get_session() as s:
        results = hybrid_search(q, s, top_k)
    return [
        schemas.SearchResultItem(chunk_id=r["id"], score=round(r["score"], 4), text=r["text"])
        for r in results
    ]


# ---------- 对话 ----------
@app.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest) -> schemas.ChatResponse:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    # 1) 词库闸门
    sensitive, synonyms, qa_hits = lexicon.process(question)
    if sensitive:
        return schemas.ChatResponse(
            answer="您的问题包含敏感词，无法回答。", source="blocked"
        )
    if qa_hits:
        return schemas.ChatResponse(
            answer=lexicon.direct_answer(qa_hits[0]), source="direct_qa"
        )

    # 2) 混合检索（同义扩展增强 query）
    augmented = question + " " + " ".join(synonyms)
    with get_session() as s:
        ranked = hybrid_search(augmented, s)
    if not ranked:
        return schemas.ChatResponse(
            answer="根据现有资料无法回答。", source="no_context"
        )
    top = [
        schemas.SearchResultItem(chunk_id=r["id"], score=round(r["score"], 4), text=r["text"])
        for r in ranked
    ]

    # 3) 生成
    try:
        answer = generate(question, [r["text"] for r in ranked])
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return schemas.ChatResponse(answer=answer, source="llm", context=top)


# ---------- 词库热更新 ----------
@app.post("/lexicon/reload", summary="重新加载词库文件")
def reload_lexicon() -> dict:
    lexicon.reload()
    return {"status": "reloaded", "path": settings.lexicon_path, "redis": _redis is not None}
