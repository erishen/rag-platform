"""Embedding 双后端核心逻辑：优先 Ollama，失败回退 sentence-transformers。

- ollama_backend.OllamaBackend ：进程外 HTTP，轻量（仅 requests），主路径
- st_backend.STBackend         ：进程内 PyTorch，重依赖，仅兜底时延迟 import 本模块

两种后端输出都 L2 归一化，便于直接算余弦相似度。
向量维度必须与 EMBED_DIM 一致（入库与检索共用同一向量空间）。
"""
from __future__ import annotations

import numpy as np

from app.config import settings
from app.embed.base import EmbedBackend


def _check_dim(vecs: np.ndarray, backend: str) -> None:
    if vecs.shape[1] != settings.embed_dim:
        raise RuntimeError(
            f"[{backend}] 向量维度 {vecs.shape[1]} 与 EMBED_DIM={settings.embed_dim} 不符，"
            f"请同步 .env 中的 EMBED_DIM 与所选模型"
        )


def _ollama_backend() -> EmbedBackend:
    from app.embed.ollama_backend import OllamaBackend

    return OllamaBackend(settings.embed_model, settings.ollama_base_url)


def _st_backend() -> EmbedBackend:
    from app.embed.st_backend import STBackend  # 延迟 import：此行才加载 torch

    return STBackend(settings.embed_model)


def embed(texts: list[str]) -> np.ndarray:
    """文本列表 -> (n, dim) float32 矩阵（已归一化）。"""
    if not texts:
        return np.zeros((0, settings.embed_dim), dtype="float32")

    prefer_ollama = settings.embed_backend.lower() in ("ollama", "auto")
    last_err: Exception | None = None

    if prefer_ollama:
        try:
            vecs = _ollama_backend().encode(texts)
            _check_dim(vecs, "ollama")
            return vecs
        except Exception as e:  # Ollama 不可用 -> 回退
            last_err = e
            print(f"[embed] Ollama 不可用，回退 sentence-transformers：{e}")

    if settings.embed_backend.lower() in ("st", "sentence-transformers") or last_err is not None:
        vecs = _st_backend().encode(texts)
        _check_dim(vecs, "sentence-transformers")
        return vecs

    raise RuntimeError(f"embedding 失败：{last_err}")


def embed_one(text: str) -> np.ndarray:
    """单条文本 -> (dim,) 一维向量（已归一化）。"""
    return embed([text])[0]
