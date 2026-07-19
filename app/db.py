"""PostgreSQL 引擎与建表（基于 SQLAlchemy 引擎）。

- 引擎连接串来自 settings.database_url（postgresql+psycopg://...）
- 首次建表需先 `CREATE EXTENSION vector`（pgvector 扩展，仅 Postgres）
"""
from sqlmodel import Session, create_engine

from app.config import settings
from app.models import SQLModel

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    # pgvector 扩展只需建一次；SQLite 不支持，跳过
    if settings.database_url.startswith("postgresql"):
        with engine.connect() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
