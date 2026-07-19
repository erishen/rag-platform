"""混合检索：pgvector 向量召回 + BM25 关键词二级融合。

对齐典型的纯向量检索方案（其只用 pgvector 向量相似度），我们额外补一路
BM25，两路各自 min-max 归一化后按权重融合，取 Top-K —— 这是生产 RAG 常见的
hybrid retrieval 做法。

向量召回直接用 pgvector 的 `cosine_distance` 在 SQL 层完成（语义余弦，比裸
L2 距离更准）。`<->` 实际是
L2 距离、再 `1 - L2` 当分数，这是个有意思的"选型细节"；我们用
`cosine_distance` 走正路。
"""
from sqlmodel import select

from app.bm25 import BM25
from app.config import settings
from app.embed import embed_one
from app.models import Chunk


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def hybrid_search(query: str, session, top_k: int | None = None) -> list[dict]:
    """向量召回走 pgvector SQL，BM25 做二级融合。

    Args:
        query: 用户问题（可含同义扩展）
        session: SQLModel Session（用于执行 pgvector 检索）
        top_k: 返回条数，默认 settings.top_k
    Returns:
        [{"id", "text", "score"}, ...] 按融合分数降序
    """
    top_k = top_k or settings.top_k
    q_vec = embed_one(query).tolist()

    # 1) pgvector 向量召回 top_k*3 候选（语义余弦，对齐向量检索）
    stmt = (
        select(
            Chunk.id,
            Chunk.text,
            (1 - Chunk.embedding.cosine_distance(q_vec)).label("vec_score"),
        )
        .order_by(Chunk.embedding.cosine_distance(q_vec))
        .limit(top_k * 3)
    )
    rows = session.exec(stmt).all()
    if not rows:
        return []

    ids = [r.id for r in rows]
    texts = [r.text for r in rows]
    vec_scores = [float(r.vec_score) for r in rows]

    # 2) BM25 二级融合（关键词命中增强）
    bm25 = BM25(texts)
    bm25_scores = bm25.score(query)

    bm25_n = _minmax(bm25_scores)
    vec_n = _minmax(vec_scores)
    fused = [
        settings.vector_weight * v + settings.bm25_weight * b
        for v, b in zip(vec_n, bm25_n)
    ]

    order = sorted(range(len(rows)), key=lambda i: fused[i], reverse=True)[:top_k]
    return [{"id": ids[i], "text": texts[i], "score": fused[i]} for i in order]
