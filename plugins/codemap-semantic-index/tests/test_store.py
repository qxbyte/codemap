"""Tests for the on-disk store (chunks.json / vectors.npy / model_id.txt / manifest.json)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from codemap_semantic_index.chunker import Chunk
from codemap_semantic_index.store import (
    ModelMismatch,
    SemanticStore,
    format_model_id,
    parse_model_id,
)


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"k::s::w{i}",
            knowledge_id="k",
            category="rules",
            title="t",
            h2_title="s",
            text=f"body {i}",
            source_md="x",
            source_yml="y",
            text_hash=f"hash{i}",
        )
        for i in range(n)
    ]


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    chunks = _make_chunks(3)
    vectors = np.random.randn(3, 8).astype(np.float32)
    model_id = "local:huggingface:fake-model"

    store.write_all(chunks, vectors, model_id)
    assert store.is_built

    back_chunks = store.load_chunks()
    back_vectors = store.load_vectors()
    back_manifest = store.load_manifest()
    back_model_id = store.load_model_id()

    assert len(back_chunks) == 3
    assert back_chunks[0].chunk_id == "k::s::w0"
    assert back_vectors is not None
    np.testing.assert_array_almost_equal(back_vectors, vectors)
    assert back_manifest == {f"k::s::w{i}": f"hash{i}" for i in range(3)}
    assert back_model_id == model_id


def test_write_rejects_chunk_vector_count_mismatch(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    chunks = _make_chunks(3)
    vectors = np.random.randn(5, 8).astype(np.float32)
    with pytest.raises(ValueError, match="chunk count"):
        store.write_all(chunks, vectors, "id")


def test_assert_model_matches_passes_when_no_file(tmp_path: Path) -> None:
    """Fresh project — no model_id.txt yet → pass silently."""
    store = SemanticStore(tmp_path)
    store.assert_model_matches("any-id")  # no raise


def test_assert_model_matches_raises_on_mismatch(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    chunks = _make_chunks(1)
    vectors = np.random.randn(1, 4).astype(np.float32)
    store.write_all(chunks, vectors, "local:huggingface:model-a")

    with pytest.raises(ModelMismatch, match="model-a"):
        store.assert_model_matches("local:huggingface:model-b")


def test_assert_model_matches_passes_on_match(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    chunks = _make_chunks(1)
    vectors = np.random.randn(1, 4).astype(np.float32)
    store.write_all(chunks, vectors, "local:huggingface:model-a")
    store.assert_model_matches("local:huggingface:model-a")  # no raise


def test_empty_store_returns_empty(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    assert not store.is_built
    assert store.load_chunks() == []
    assert store.load_vectors() is None
    assert store.load_manifest() == {}
    assert store.load_model_id() is None


def test_atomic_write_no_tmp_left_behind(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    chunks = _make_chunks(2)
    vectors = np.random.randn(2, 8).astype(np.float32)
    store.write_all(chunks, vectors, "id")

    # No leftover .tmp files in the _semantic dir
    leftovers = list(store.root.glob("*.tmp"))
    assert leftovers == []


def test_format_and_parse_model_id_roundtrip() -> None:
    assert format_model_id("local", "huggingface", "X/Y") == "local:huggingface:X/Y"
    parsed = parse_model_id("openai_compatible:qwen:text-embedding-v3")
    assert parsed.backend == "openai_compatible"
    assert parsed.provider == "qwen"
    assert parsed.model == "text-embedding-v3"


def test_parse_model_id_rejects_malformed() -> None:
    with pytest.raises(ValueError, match="malformed"):
        parse_model_id("just-a-name")


def test_corrupt_chunks_json_returns_empty(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    store.root.mkdir(parents=True)
    store.chunks_path.write_text("{not valid json")
    assert store.load_chunks() == []


def test_corrupt_vectors_npy_returns_none(tmp_path: Path) -> None:
    store = SemanticStore(tmp_path)
    store.root.mkdir(parents=True)
    store.vectors_path.write_text("garbage not numpy")
    assert store.load_vectors() is None
