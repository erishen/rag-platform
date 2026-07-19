"""sentence-transformers embedding 后端（进程内 PyTorch）。

重依赖（torch）。本模块仅作为 Ollama 兜底、由 embed 包延迟 import，
因此下面的顶部 import 也只在该模块被加载时才触发 torch，不影响 ollama 为主路径的启动速度。
"""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from app.embed.base import EmbedBackend


class STBackend(EmbedBackend):
    def __init__(self, model: str) -> None:
        self._model = SentenceTransformer(model)

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(vecs, dtype="float32")
