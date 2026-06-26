"""Tests for the embed pipeline (rebuild_index + incremental_index).

Uses a deterministic stub backend (no sentence-transformers, no network)
so the indexer logic is exercised in isolation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from codemap_semantic_index.indexer import (
    IndexResult,
    incremental_index,
    rebuild_index,
)
from codemap_semantic_index.store import ModelMismatch, SemanticStore


class _FakeBackend:
    """Maps each text to a deterministic 4-dim unit vector."""

    dimensions = 4
    model_id = "local:huggingface:fake-model"

    def __init__(self) -> None:
        self.call_count = 0
        self.last_batch_size = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.call_count += 1
        self.last_batch_size = len(texts)
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()[:16]
            ints = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
            vec = ints.reshape(4, 4).mean(axis=1)  # 4-dim
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            out.append(vec)
        return np.asarray(out, dtype=np.float32)


def _seed_kb(tmp_path: Path) -> None:
    rules = tmp_path / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-a.yml.md").unlink(missing_ok=True)
    (rules / "rule-a.md").write_text(
        "# rule a\n\n## why\n\nbecause reasons.\n",
        encoding="utf-8",
    )
    (rules / "rule-b.md").write_text(
        "# rule b\n\n## why\n\nother reasons.\n",
        encoding="utf-8",
    )


def test_rebuild_writes_store_for_seeded_project(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    backend = _FakeBackend()
    result = rebuild_index(tmp_path, backend)
    assert isinstance(result, IndexResult)
    assert result.mode == "rebuild"
    assert result.n_total == result.n_encoded
    assert result.n_total > 0
    assert result.n_reused == 0

    store = SemanticStore(tmp_path)
    assert store.is_built
    assert store.load_model_id() == "local:huggingface:fake-model"
    vecs = store.load_vectors()
    assert vecs is not None
    assert vecs.shape == (result.n_total, 4)


def test_rebuild_empty_project_writes_empty_store(tmp_path: Path) -> None:
    backend = _FakeBackend()
    result = rebuild_index(tmp_path, backend)
    assert result.n_total == 0
    store = SemanticStore(tmp_path)
    assert store.is_built
    vecs = store.load_vectors()
    assert vecs is not None
    assert vecs.shape == (0, 4)


def test_incremental_reuses_unchanged_chunks(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    backend = _FakeBackend()
    first = rebuild_index(tmp_path, backend)
    n_first_calls = backend.call_count

    # Run incremental — nothing changed, all chunks reused.
    second = incremental_index(tmp_path, backend)
    assert second.n_reused == first.n_total
    assert second.n_encoded == 0
    assert backend.call_count == n_first_calls  # no new call


def test_incremental_encodes_only_changed_chunks(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    backend = _FakeBackend()
    rebuild_index(tmp_path, backend)
    pre_calls = backend.call_count

    # Modify rule-a; rule-b unchanged
    (tmp_path / "knowledge-base" / "rules" / "rule-a.md").write_text(
        "# rule a\n\n## why\n\nCOMPLETELY DIFFERENT.\n",
        encoding="utf-8",
    )
    result = incremental_index(tmp_path, backend)
    # rule-a has 1 chunk that changed → encoded 1; rule-b's reused
    assert result.n_encoded == 1
    assert result.n_reused >= 1
    assert backend.call_count == pre_calls + 1
    assert backend.last_batch_size == 1


def test_incremental_handles_deleted_files(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    backend = _FakeBackend()
    first = rebuild_index(tmp_path, backend)

    (tmp_path / "knowledge-base" / "rules" / "rule-b.md").unlink()
    second = incremental_index(tmp_path, backend)
    # rule-b chunks gone
    assert second.n_total < first.n_total
    assert second.n_removed >= 1


def test_incremental_raises_on_model_mismatch(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    rebuild_index(tmp_path, _FakeBackend())

    class _OtherBackend(_FakeBackend):
        model_id = "openai_compatible:qwen:text-embedding-v3"

    with pytest.raises(ModelMismatch):
        incremental_index(tmp_path, _OtherBackend())


def test_rebuild_clears_old_model_mismatch(tmp_path: Path) -> None:
    """rebuild_index ignores any existing store → never raises on mismatch."""
    _seed_kb(tmp_path)
    rebuild_index(tmp_path, _FakeBackend())

    class _OtherBackend(_FakeBackend):
        model_id = "openai_compatible:qwen:text-embedding-v3"

    # Should rebuild cleanly, overwriting model_id.txt
    result = rebuild_index(tmp_path, _OtherBackend())
    assert result.mode == "rebuild"
    store = SemanticStore(tmp_path)
    assert store.load_model_id() == "openai_compatible:qwen:text-embedding-v3"


def test_rebuild_on_corrupt_store_works(tmp_path: Path) -> None:
    _seed_kb(tmp_path)
    backend = _FakeBackend()
    rebuild_index(tmp_path, backend)
    # Corrupt vectors.npy
    SemanticStore(tmp_path).vectors_path.write_text("garbage")
    # Incremental should fall back to rebuild
    result = incremental_index(tmp_path, backend)
    assert result.mode == "rebuild"
    assert result.n_total > 0
