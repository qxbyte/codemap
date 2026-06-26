"""Common protocol every embedding backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

__all__ = ["EmbeddingBackend"]


@runtime_checkable
class EmbeddingBackend(Protocol):
    """All backends produce L2-normalised float32 vectors of the same
    dimension. Caller stacks the per-text outputs into the project's
    ``vectors.npy`` matrix.

    Implementations MUST:

    * Return one vector per input text, in input order
    * Normalise vectors to unit length so the recall hook can use plain
      dot-product as cosine similarity
    * Cope with empty input list → return empty ``(0, dim)`` array
    """

    #: The vector dimension this backend produces (e.g. 1024).
    dimensions: int

    #: A model fingerprint string formatted by
    #: :func:`codemap_semantic_index.store.format_model_id`. Recall /
    #: embed compare this against on-disk ``model_id.txt``.
    model_id: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode a batch of texts. Returns shape ``(len(texts), dimensions)``,
        dtype ``float32``, L2-normalised rows."""
        ...
