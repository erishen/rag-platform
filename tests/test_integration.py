"""集成冒烟测试：打真实 PG+pgvector（无基建自动 skip）。

覆盖完整请求链路：探活 / 入库 / 检索 / 词库闸门拦截 / 直答 / 无 key 报错 /
词库热更新。embedding 由 conftest 的桩注入，不依赖真实模型。
"""
import pytest

pytestmark = pytest.mark.integration


def test_health(pg_client):
    r = pg_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ingest_and_search(pg_client):
    r = pg_client.post(
        "/ingest",
        json={
            "title": "退款说明",
            "content": "本店商品支持7天无理由退款。退款将原路返回到您的支付账户。"
            "营业时间为每日09:00至22:00。",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("doc_id"), int)
    assert body.get("chunks", 0) >= 1

    r = pg_client.get("/search", params={"q": "退款"})
    assert r.status_code == 200
    results = r.json()
    assert len(results) >= 1
    assert any("退款" in item["text"] for item in results)


def test_chat_blocked(pg_client):
    r = pg_client.post("/chat", json={"question": "讲讲暴力内容"})
    assert r.status_code == 200
    assert r.json()["source"] == "blocked"


def test_chat_direct_qa(pg_client):
    r = pg_client.post("/chat", json={"question": "营业时间"})
    assert r.status_code == 200
    assert r.json()["source"] == "direct_qa"


def test_chat_no_key_returns_500(pg_client):
    r = pg_client.post("/chat", json={"question": "退款多久到账"})
    assert r.status_code == 500


def test_lexicon_reload(pg_client):
    r = pg_client.post("/lexicon/reload")
    assert r.status_code == 200
