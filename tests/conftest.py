"""pytest 共享配置：env 预设 + 桩 embedding fixture + PG 集成 fixture。

注意：EMBED_DIM / DATABASE_URL 必须在 import app 之前设定
（app.models 在导入时用 settings.embed_dim 固化 Vector 列维度），故写在最顶部。
"""
import os

# 注意：必须用硬赋值而非 setdefault —— `uv run` 会自动加载 .env（其中 EMBED_DIM=1024、
# DATABASE_URL 指向开发库 rag），会抢先 setdefault，导致建表维度(1024) 与桩向量维度(512)
# 不匹配、或测试误连开发库清空其数据。这里强制指向独立的 rag_test 库。
os.environ["EMBED_DIM"] = "512"
os.environ["DATABASE_URL"] = "postgresql+psycopg://rag:rag@localhost:5432/rag_test"
os.environ["OPENAI_API_KEY"] = ""  # 集成测试要验证「无 key → 500」

import re

import numpy as np
import pytest
from sqlalchemy import create_engine, text


def fake_embed(texts):
    """确定性伪向量（避免 torch/Ollama）。

    维度跟随 EMBED_DIM，确保与 app.models 建表时的 Vector 列维度一致，
    避免因硬编码维度与 settings.embed_dim 不符而触发 pgvector 维度不匹配。
    """
    dim = int(os.environ.get("EMBED_DIM", "512"))
    out = []
    for t in texts:
        rng = np.random.RandomState(abs(hash(t)) % (2**32))
        v = rng.randn(dim).astype("float32")
        v /= np.linalg.norm(v)
        out.append(v)
    return np.array(out, dtype="float32")


@pytest.fixture
def fake_embed_stub():
    """确定性伪向量（避免 torch/Ollama），返回 (n, 512) 归一化矩阵。"""
    return fake_embed


@pytest.fixture
def pg_client(monkeypatch):
    """连真实 PG+pgvector 的 TestClient；无基建则自动 skip。

    集成测试使用独立的 `rag_test` 库（不碰开发库 `rag`）。若测试库不存在，
    则连维护库 `postgres` 按需创建之（CREATE DATABASE 需 autocommit）。

    桩 embedding 通过 monkeypatch 注入 app.embed / app.retriever / app.main，
    因此集成测试不依赖任何真实模型。
    """
    import app.db as db
    import app.main as m
    import app.retriever as rt
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel

    test_url = m.settings.database_url  # .../rag_test（由 conftest 顶部硬设）
    admin_url = re.sub(r"/[^/]+$", "/postgres", test_url)

    # 1) 确保测试库存在：连维护库，autocommit 下 CREATE DATABASE
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            # 注意：exec_driver_sql 不识别 SQLAlchemy 的 :name 占位符，需用 text() 绑定参数
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": "rag_test"}
            ).first()
            if not exists:
                conn.exec_driver_sql("CREATE DATABASE rag_test")
    except Exception as e:  # 无 PG / 无权限
        pytest.skip(f"无法连接 PG 以准备测试库（需先 `make infra-up`）：{e}")
    finally:
        admin_engine.dispose()

    # 2) 连测试库，建 pgvector 扩展 + schema
    engine = db.create_engine(test_url, connect_args={})
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
    except Exception as e:  # 无 pgvector 扩展
        pytest.skip(f"PG+pgvector 不可用（需先 `make infra-up`）：{e}")

    db.engine = engine
    # 先 drop 再 create：保证 chunk 列的 Vector 维度与当前 EMBED_DIM 一致，
    # 避免旧 schema（如切换 EMBED_DIM 前残留的 1024 维表）导致维度不匹配。
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    m.lexicon = m.Lexicon(m.settings.lexicon_path)

    stub = fake_embed
    monkeypatch.setattr("app.embed.embed", stub)
    monkeypatch.setattr("app.embed.embed_one", lambda t: stub([t])[0])
    monkeypatch.setattr(rt, "embed_one", lambda t: stub([t])[0])
    monkeypatch.setattr(m, "embed", stub)

    # 用 with 进入 lifespan：触发 startup（init_db / 启动轮询），退出时触发 shutdown
    # （取消轮询任务），避免后台任务泄漏。
    with TestClient(m.app) as client:
        yield client
