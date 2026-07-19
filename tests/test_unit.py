"""无需基建的纯单元测试：BM25 / 词库闸门 / 文本分块 / 融合归一化。

这些用例不连 PG/Redis，可在 CI / 沙箱里稳定跑过，作为日常回归闸门。
"""
from app.bm25 import BM25
from app.lexicon import Lexicon
from app.retriever import _minmax
from app.splitter import split_text


def test_bm25_ranks_relevant_doc_higher():
    docs = ["退款将原路返回到支付账户", "营业时间为每日09点至22点"]
    bm = BM25(docs)
    scores = bm.score("退款")
    assert scores[0] > scores[1]  # 「退款」只出现在第一篇


def test_bm25_empty_query_returns_zeros():
    bm = BM25(["a", "b"])
    assert bm.score("") == [0.0, 0.0]


def test_lexicon_blocks_sensitive_and_direct_answers(tmp_path):
    lex = tmp_path / "lexicon.json"
    lex.write_text(
        '{"sensitive": ["暴力"], "synonyms": {"退钱": "退款"},'
        ' "direct_qa": [{"keywords": ["营业时间"], "answer": "营业时间09:00-22:00"}]}',
        encoding="utf-8",
    )
    lc = Lexicon(str(lex), redis_client=None)
    # 查询同时含敏感词「暴力」与直答关键词「营业时间」，验证两者都能被命中
    sensitive, synonyms, qa = lc.process("暴力相关的营业时间咨询")
    assert sensitive == {"暴力"}
    assert synonyms == set()
    assert qa == [0]
    assert "09:00" in lc.direct_answer(0)


def test_lexicon_synonym_expansion(tmp_path):
    lex = tmp_path / "lexicon.json"
    lex.write_text(
        '{"sensitive": [], "synonyms": {"退钱": "退款"}, "direct_qa": []}',
        encoding="utf-8",
    )
    lc = Lexicon(str(lex), redis_client=None)
    _, synonyms, _ = lc.process("我要退钱")
    assert synonyms == {"退款"}


def test_split_text_basic():
    # 短文本在默认 max_len 下按句累积为 1 块（分块器是累积而非逐句成块）
    chunks = split_text("第一句。第二句。第三句。")
    assert len(chunks) == 1
    assert chunks[0] == "第一句。第二句。第三句。"


def test_split_text_long_text_splits():
    text = "这是一段很长的中文文本。" * 50  # 远超 max_len
    chunks = split_text(text, max_len=40, overlap=10)
    assert len(chunks) > 1


def test_minmax_normalization():
    assert _minmax([1, 2, 3]) == [0.0, 0.5, 1.0]
    assert _minmax([]) == []
    assert _minmax([5, 5]) == [0.0, 0.0]  # 区间过窄 -> 全 0
