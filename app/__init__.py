"""rag-platform：一个极简 RAG 学习项目。

架构分层：
  1. 词库闸门 lexicon  —— AhoCorasick 多模式匹配，做敏感词拦截 / 同义扩展 / 问答直答
  2. 混合检索 retriever —— BM25（关键词）+ 向量（语义）双路召回后融合
  3. 生成 generator    —— OpenAI 兼容 LLM，只依据检索到的上下文作答

设计取舍（为可运行而简化）：
  - 存储用 SQLite + numpy 存向量，替代 PostgreSQL/pgvector
  - 去掉 Redis，词库改为内存加载 + /lexicon/reload 热更新
  - 审核状态机简化为 active/disabled 两态
  - embedding 用 sentence-transformers 本地推理，替代 CUDA BGE
"""
