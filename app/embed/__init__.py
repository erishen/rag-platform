"""Embedding 双后端：优先 Ollama，失败回退 sentence-transformers（拆子模块，薄门面）。

结构：
- base.py               ：后端抽象基类 EmbedBackend
- ollama_backend.py     ：Ollama HTTP 后端（仅 requests，主路径）
- st_backend.py         ：sentence-transformers 后端（重依赖，仅兜底时延迟 import）
- core.py               ：后端选择 + 维度守卫 + 公共 API（真正逻辑在此）
"""
from app.embed.core import embed, embed_one

__all__ = ["embed", "embed_one"]
