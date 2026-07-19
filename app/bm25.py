"""从零实现的 Okapi BM25（jieba 分词）。

BM25 是经典的关键词相关性排序：一个词在文档中出现多（TF 高）、
但在整个语料中稀有（IDF 高）→ 该文档更相关，并对文档长度做归一化。

典型的向量检索方案只用向量，本文件是「混合检索」额外补的 BM25 一路。
"""
import math
from collections import defaultdict

import jieba


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = [self._tokenize(d) for d in docs]
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / self.N if self.N else 0.0
        self.f = []          # 每篇文档的 term->freq
        self.df = defaultdict(int)  # term 的文档频率
        for doc in self.docs:
            tf: dict[str, int] = defaultdict(int)
            for w in doc:
                tf[w] += 1
            self.f.append(dict(tf))
            for w in tf:
                self.df[w] += 1

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return jieba.lcut(text)

    def score(self, query: str) -> list[float]:
        """返回每篇文档对 query 的 BM25 分数。"""
        q_tokens = self._tokenize(query)
        scores = []
        for i, doc in enumerate(self.docs):
            dl = len(doc)
            score = 0.0
            for w in q_tokens:
                if w not in self.f[i]:
                    continue
                idf = math.log(1 + (self.N - self.df[w] + 0.5) / (self.df[w] + 0.5))
                tf = self.f[i][w]
                score += idf * (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            scores.append(score)
        return scores
