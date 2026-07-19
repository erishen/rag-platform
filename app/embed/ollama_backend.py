"""Ollama embedding 后端（进程外 HTTP，批量 /api/embed）。"""
from __future__ import annotations

import numpy as np
import requests

from app.embed.base import EmbedBackend


class OllamaBackend(EmbedBackend):
    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.url = f"{base_url.rstrip('/')}/api/embed"

    def encode(self, texts: list[str]) -> np.ndarray:
        resp = requests.post(
            self.url, json={"model": self.model, "input": texts}, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()["embeddings"]
        out = np.asarray(data, dtype="float32")
        norms = np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
        return out / norms
