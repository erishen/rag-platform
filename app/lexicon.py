"""词库闸门：AhoCorasick 多模式匹配，缓存进 Redis。

典型做法：
  - 词库 JSON 缓存进 Redis，定时轮询源是否变化，变化则重建匹配器写回 Redis
  - 精确匹配永远排在向量语义检索之前（敏感词拦截 / 问答对直答最便宜）

本项目的词库来源为一个 JSON 文件（`data/lexicon.json`）；生产 RAG 通常从数据库表拉取词库，二者逻辑一致。

Redis 容错：若未传入 redis 客户端或连接失败，自动回退为纯内存模式
（仍可用，只是没有跨进程缓存 / 轮询重建能力）——方便 `make test` 无 Redis 跑通。
"""
import json
import threading
from datetime import datetime, timezone

import ahocorasick


LEXICON_KEY = "rag:lexicon"  # 词库 JSON（sensitive/synonyms/direct_qa）
LEXICON_VERSION_KEY = "rag:lexicon-version"  # 词库写回 Redis 的版本时间戳
LEXICON_REFRESH_KEY = "rag:lexicon-refresh"  # 外部触发重建的刷新信号时间戳


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class Lexicon:
    def __init__(self, source_path: str, redis_client=None):
        self.path = source_path
        self.r = redis_client  # None -> 内存模式
        self._lock = threading.Lock()
        self._auto = None
        self.sensitive: set[str] = set()
        self.synonyms: dict[str, str] = {}
        self.direct_qa: list[dict] = []
        self.update_ts = 0
        self._load()

    # ---------- 内部：加载 / 重建 ----------
    def _load(self) -> None:
        # 优先从 Redis 恢复（多进程共享缓存）；缺失或不可用则回源文件重建
        if self.r is not None:
            try:
                raw = self.r.get(LEXICON_KEY)
                if raw:
                    self._apply(json.loads(raw))
                    self.update_ts = int(self.r.get(LEXICON_VERSION_KEY) or 0)
                    return
            except Exception:
                pass
        self._rebuild()

    def _apply(self, data: dict) -> None:
        with self._lock:
            self.sensitive = set(data.get("sensitive", []))
            self.synonyms = data.get("synonyms", {})
            self.direct_qa = data.get("direct_qa", [])
            auto = ahocorasick.Automaton()
            for w in self.sensitive:
                auto.add_word(w, ("sensitive", w))
            for alias, canon in self.synonyms.items():
                auto.add_word(alias, ("synonym", canon))
            for idx, item in enumerate(self.direct_qa):
                for kw in item.get("keywords", []):
                    auto.add_word(kw, ("qa", idx))
            auto.make_automaton()
            self._auto = auto

    def _rebuild(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"[warn] 词库文件不存在: {self.path}，使用空词库")
            data = {"sensitive": [], "synonyms": {}, "direct_qa": []}
        self._apply(data)
        if self.r is not None:
            try:
                self.r.set(LEXICON_KEY, json.dumps(data, ensure_ascii=False))
                self.r.set(LEXICON_VERSION_KEY, _now_ts())
            except Exception:
                pass

    # ---------- 对外：热更新 / 轮询 ----------
    def reload(self) -> None:
        """/lexicon/reload 触发：立即重建并写回 Redis，同时置刷新信号。"""
        self._rebuild()
        if self.r is not None:
            try:
                self.r.set(LEXICON_REFRESH_KEY, _now_ts())
            except Exception:
                pass

    def check_update(self) -> None:
        """后台轮询任务：发现刷新信号则重建。"""
        if self.r is None:
            return
        try:
            refresh_ts = int(self.r.get(LEXICON_REFRESH_KEY) or 0)
            version_ts = int(self.r.get(LEXICON_VERSION_KEY) or 0)
        except Exception:
            return
        if refresh_ts > version_ts or self.update_ts == 0:
            self._rebuild()

    # ---------- 对外：匹配 ----------
    def process(self, text: str) -> tuple[set[str], set[str], list[int]]:
        """扫描文本，返回 (敏感词集合, 扩展出的规范词集合, 命中的问答对索引列表)。"""
        sensitive_hits: set[str] = set()
        synonyms_hits: set[str] = set()
        qa_hits: list[int] = []
        with self._lock:
            for _end, (kind, val) in self._auto.iter(text):
                if kind == "sensitive":
                    sensitive_hits.add(val)
                elif kind == "synonym":
                    synonyms_hits.add(val)
                elif kind == "qa":
                    qa_hits.append(val)
        return sensitive_hits, synonyms_hits, qa_hits

    def direct_answer(self, qa_index: int) -> str:
        return self.direct_qa[qa_index]["answer"]
