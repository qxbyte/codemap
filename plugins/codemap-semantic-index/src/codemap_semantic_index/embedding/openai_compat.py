"""OpenAI-compatible cloud embedding backend.

Targets any provider that speaks the ``POST {base_url}/embeddings``
shape:

    Request  : {"model": str, "input": list[str], "dimensions": int?}
    Response : {"data": [{"embedding": list[float]}, ...]}

Verified providers: Qwen DashScope, OpenAI, Zhipu, Voyage, self-hosted
vLLM / Ollama / TEI."""

from __future__ import annotations

from collections.abc import Iterable

import httpx
import numpy as np

from codemap_semantic_index.embedding.base import EmbeddingBackend
from codemap_semantic_index.store import format_model_id

__all__ = ["OpenAICompatibleBackend"]


_DEFAULT_BATCH = 32
_DEFAULT_TIMEOUT = 60.0


class OpenAICompatibleBackend(EmbeddingBackend):
    """One backend instance per ``EmbeddingConfig``.

    The HTTP client is held on the instance; reuse across many
    ``encode()`` calls amortises TCP / TLS setup."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        provider: str = "openai_compatible",
        batch_size: int = _DEFAULT_BATCH,
        timeout: float = _DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required for openai_compat backend")
        if not api_key:
            raise ValueError("api_key is required for openai_compat backend")
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.provider = provider
        self.batch_size = batch_size
        self.timeout = timeout
        self.model_id = format_model_id("openai_compatible", provider, model)
        self._client = http_client or httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    # ---------- protocol ----------

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        all_vectors: list[list[float]] = []
        for batch in _batched(texts, self.batch_size):
            all_vectors.extend(self._encode_batch(batch))
        arr = np.asarray(all_vectors, dtype=np.float32)
        return _l2_normalise(arr)

    # ---------- internals ----------

    def _encode_batch(self, batch: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self.model,
            "input": batch,
            "dimensions": self.dimensions,
        }
        resp = self._client.post(f"{self.base_url}/embeddings", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"embedding API returned HTTP {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(batch):
            raise RuntimeError(f"unexpected embedding API response shape: {body!r}")
        out: list[list[float]] = []
        for entry in data:
            if not isinstance(entry, dict):
                raise RuntimeError(f"unexpected data entry: {entry!r}")
            emb = entry.get("embedding")
            if not isinstance(emb, list):
                raise RuntimeError(f"unexpected embedding entry: {entry!r}")
            if len(emb) != self.dimensions:
                raise RuntimeError(f"embedding dim {len(emb)} != expected {self.dimensions}")
            out.append([float(x) for x in emb])
        return out

    def close(self) -> None:
        self._client.close()


# ---------- helpers ----------


def _batched(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _l2_normalise(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (arr / norms).astype(np.float32, copy=False)
