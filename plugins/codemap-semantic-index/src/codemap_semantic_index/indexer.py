"""Main embed pipeline: chunk → embed → write store.

Two modes:

* **Full rebuild** (``rebuild_index``) — re-chunks everything, encodes
  every chunk with the active backend, writes new store. Used on first
  install, after model swap, or when the user passes ``--rebuild``.

* **Incremental** (``incremental_index``) — re-chunks everything, but
  only encodes chunks whose ``text_hash`` doesn't match the on-disk
  manifest. Hash-stable chunks keep their existing vectors; new /
  modified chunks get re-encoded; chunks no longer present are dropped.

Both functions return an :class:`IndexResult` summarising what happened
so the CLI can render a brief report."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from codemap_semantic_index.chunker import Chunk, chunk_knowledge_base
from codemap_semantic_index.embedding.base import EmbeddingBackend
from codemap_semantic_index.store import SemanticStore

__all__ = ["IndexResult", "incremental_index", "rebuild_index"]


@dataclass(frozen=True)
class IndexResult:
    n_total: int
    n_encoded: int  # how many actually went through the backend
    n_reused: int  # vector copied from existing store
    n_removed: int  # chunks gone since last run
    mode: str  # "rebuild" | "incremental"
    model_id: str


def rebuild_index(
    project_root: Path,
    backend: EmbeddingBackend,
) -> IndexResult:
    """Re-encode every chunk from scratch, ignoring any existing store."""
    store = SemanticStore(project_root)
    chunks = chunk_knowledge_base(project_root)
    if not chunks:
        # Write empty store so subsequent recall short-circuits cleanly.
        empty = np.zeros((0, backend.dimensions), dtype=np.float32)
        store.write_all(chunks=[], vectors=empty, model_id=backend.model_id)
        return IndexResult(
            n_total=0,
            n_encoded=0,
            n_reused=0,
            n_removed=0,
            mode="rebuild",
            model_id=backend.model_id,
        )
    texts = [c.text for c in chunks]
    vectors = backend.encode(texts)
    store.write_all(chunks=chunks, vectors=vectors, model_id=backend.model_id)
    return IndexResult(
        n_total=len(chunks),
        n_encoded=len(chunks),
        n_reused=0,
        n_removed=0,
        mode="rebuild",
        model_id=backend.model_id,
    )


def incremental_index(
    project_root: Path,
    backend: EmbeddingBackend,
) -> IndexResult:
    """Encode only chunks whose text hash changed.

    Refuses to run when the on-disk store was built with a different
    model (raises :class:`store.ModelMismatch`) — caller should fall
    back to ``rebuild_index`` after asking the user."""
    store = SemanticStore(project_root)
    store.assert_model_matches(backend.model_id)  # may raise ModelMismatch

    new_chunks = chunk_knowledge_base(project_root)
    if not new_chunks:
        empty = np.zeros((0, backend.dimensions), dtype=np.float32)
        store.write_all(chunks=[], vectors=empty, model_id=backend.model_id)
        return IndexResult(
            n_total=0,
            n_encoded=0,
            n_reused=0,
            n_removed=0,
            mode="incremental",
            model_id=backend.model_id,
        )

    # Build maps for the existing store keyed by chunk_id → (chunk, vector).
    old_chunks = store.load_chunks() if store.is_built else []
    old_vectors = store.load_vectors() if store.is_built else None
    if old_vectors is None or len(old_chunks) != old_vectors.shape[0]:
        # Store mismatched / corrupt → degrade to rebuild.
        return rebuild_index(project_root, backend)

    old_by_id: dict[str, tuple[int, Chunk]] = {c.chunk_id: (i, c) for i, c in enumerate(old_chunks)}

    reused_rows: list[np.ndarray] = []
    to_encode_idx: list[int] = []  # indices into new_chunks
    for n_idx, nc in enumerate(new_chunks):
        prev = old_by_id.get(nc.chunk_id)
        if prev is not None and prev[1].text_hash == nc.text_hash:
            reused_rows.append(old_vectors[prev[0]])
            # Mark slot None so it doesn't get assigned later.
            reused_rows[-1] = old_vectors[prev[0]]
        else:
            to_encode_idx.append(n_idx)
            reused_rows.append(None)  # placeholder; will be filled  # type: ignore[arg-type]

    n_reused = sum(1 for r in reused_rows if r is not None)

    if to_encode_idx:
        texts = [new_chunks[i].text for i in to_encode_idx]
        new_vectors = backend.encode(texts)
        for placeholder_pos, v in zip(to_encode_idx, new_vectors, strict=True):
            reused_rows[placeholder_pos] = v

    # All slots filled now — stack.
    final_vectors = np.vstack(reused_rows).astype(np.float32, copy=False)
    store.write_all(
        chunks=new_chunks,
        vectors=final_vectors,
        model_id=backend.model_id,
    )

    n_removed = len(old_chunks) - sum(
        1 for c in old_chunks if c.chunk_id in {nc.chunk_id for nc in new_chunks}
    )
    return IndexResult(
        n_total=len(new_chunks),
        n_encoded=len(to_encode_idx),
        n_reused=n_reused,
        n_removed=n_removed,
        mode="incremental",
        model_id=backend.model_id,
    )


# Re-export so callers can catch a single symbol.
__all__.append("ModelMismatch")  # type: ignore[misc]
