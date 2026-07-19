"""SQLModel 数据表定义。

对应典型的 Document / 向量表设计，这里用三张轻量表：
  - Document：原始文档（标题 + 正文）
  - Chunk：文档切分后的片段，embedding 存为 pgvector 的 Vector(EMBED_DIM) 列
  - QAPair：可直接命中返回的问答对（由词库层直答，不走 LLM）

存储层：向量不再以 bytes 塞 SQLite，而是用 PostgreSQL + pgvector
的 `Vector` 列，检索走 `cosine_distance` 裸 SQL（见 app/retriever.py）。
"""
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    content: str
    status: str = Field(default="active")  # active / disabled
    created_at: str = Field(default_factory=_now)


class Chunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    text: str
    # pgvector 向量列：维度由 EMBED_DIM 决定（列维度在建表后固定，改维度需重建表）
    # 注意：sa_column 必须包一层 Column(...)，否则 SQLModel 会回退按 list 注解推断类型而报错
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(settings.embed_dim))
    )


class QAPair(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    question: str
    answer: str
    status: str = Field(default="active")
