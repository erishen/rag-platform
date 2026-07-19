"""Embedding 后端抽象基类。"""
from __future__ import annotations

import numpy as np


class EmbedBackend:
    """统一接口：文本列表 -> (n, dim) float32 矩阵（行已 L2 归一化）。"""

    def encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError
