"""Local sentence-transformers backend.

Lazy-imports ``sentence_transformers`` because the package is heavy
(pulls torch + transformers + a 100MB-1.3GB model on first encode). On
ARM Linux / unusual platforms where torch fails to import we raise a
clear actionable error rather than letting the user see a torch trace."""

from __future__ import annotations

import sys

import numpy as np

from codemap_semantic_index.embedding.base import EmbeddingBackend
from codemap_semantic_index.store import format_model_id

__all__ = ["LocalBackend"]


_DEFAULT_BATCH = 16


class LocalBackend(EmbeddingBackend):
    """One backend instance per model. The underlying SentenceTransformer
    is lazily constructed at first ``encode()`` call so plain imports
    (e.g. CLI ``--help``) don't pay the torch boot cost."""

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        batch_size: int = _DEFAULT_BATCH,
        provider: str = "huggingface",
    ) -> None:
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.provider = provider
        self.model_id = format_model_id("local", provider, model)
        self._model = None  # type: ignore[var-annotated]

    # ---------- protocol ----------

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        st_model = self._ensure_model()
        # sentence-transformers returns numpy when ``convert_to_numpy=True``.
        vectors = st_model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,  # cosine ↔ dot product
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] != self.dimensions:
            raise RuntimeError(
                f"model {self.model!r} produced shape {arr.shape}, expected (N, {self.dimensions})"
            )
        return arr

    # ---------- lazy load ----------

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised on real install
            sys.stderr.write(
                "ERROR: sentence-transformers is not installed.\n"
                "Install: pip install 'codemap-semantic-index'\n"
                "(default install already includes sentence-transformers; "
                "you may have used --no-deps).\n"
            )
            raise SystemExit(2) from exc
        # First-time download: stderr progress bar from hf_hub is fine.
        self._model = SentenceTransformer(self.model)
        return self._model
