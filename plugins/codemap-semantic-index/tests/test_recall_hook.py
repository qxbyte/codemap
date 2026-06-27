"""Tests for the recall_hook.rank entry-point.

Same _FakeBackend trick as test_indexer to avoid sentence-transformers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
from codemap_semantic_index import recall_hook
from codemap_semantic_index.indexer import rebuild_index


class _FakeBackend:
    dimensions = 4
    model_id = "local:huggingface:fake-model"

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()[:16]
            ints = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
            vec = ints.reshape(4, 4).mean(axis=1)
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            out.append(vec)
        return np.asarray(out, dtype=np.float32)


def _seed_and_build(tmp_path: Path) -> None:
    rules = tmp_path / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-coupon-mutex.md").write_text(
        "# coupon mutex\n\n## why\n\ncoupons and points cannot stack\n",
        encoding="utf-8",
    )
    (rules / "rule-vip-perk.md").write_text(
        "# vip perk\n\n## what\n\nvip users skip queues\n",
        encoding="utf-8",
    )
    # Build the store with the fake backend
    rebuild_index(tmp_path, _FakeBackend())


def test_rank_returns_empty_when_store_not_built(tmp_path: Path) -> None:
    result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert result == []


def test_rank_returns_candidates_when_store_built(tmp_path: Path) -> None:
    _seed_and_build(tmp_path)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert isinstance(result, list)
    assert all(isinstance(e, dict) for e in result)
    ids = {e["knowledge_id"] for e in result}
    assert ids <= {"rule-coupon-mutex", "rule-vip-perk"}


def test_rank_aggregates_chunks_to_knowledge_ids(tmp_path: Path) -> None:
    """A knowledge with multiple chunks should produce ONE entry (best
    chunk score wins)."""
    rules = tmp_path / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-multi.md").write_text(
        "# multi\n\n## section a\n\ntext alpha\n\n## section b\n\ntext beta\n",
        encoding="utf-8",
    )
    rebuild_index(tmp_path, _FakeBackend())
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("alpha", tmp_path, base_candidates=[])
    # Only one entry for rule-multi
    multi_entries = [e for e in result if e["knowledge_id"] == "rule-multi"]
    assert len(multi_entries) == 1


def test_rank_entry_carries_required_shape(tmp_path: Path) -> None:
    _seed_and_build(tmp_path)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert result, "expected at least one candidate"
    e = result[0]
    # Required keys per hook contract
    for key in (
        "knowledge_id",
        "type",
        "category",
        "title",
        "summary",
        "file",
        "score",
        "freshness_score",
        "stale",
    ):
        assert key in e, f"missing {key} in {e}"
    assert e["type"] in {"business_rule", "business_process", "module_map", "case", "pitfall", ""}
    assert e["category"] == "rules"
    assert e["file"].endswith(".yml")


def test_rank_returns_empty_on_model_mismatch(tmp_path: Path) -> None:
    """Built store with one model, then ask hook to use another → empty."""
    _seed_and_build(tmp_path)

    class _OtherBackend(_FakeBackend):
        model_id = "openai_compatible:qwen:text-embedding-v3"

    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_OtherBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert result == []


def test_rank_returns_empty_when_backend_construction_fails(tmp_path: Path) -> None:
    _seed_and_build(tmp_path)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        side_effect=ValueError("missing key"),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert result == []


def test_rank_returns_empty_when_encode_fails(tmp_path: Path) -> None:
    _seed_and_build(tmp_path)

    class _BrokenBackend(_FakeBackend):
        def encode(self, texts):
            raise RuntimeError("network down")

    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_BrokenBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert result == []


def test_rank_results_sorted_by_score_desc(tmp_path: Path) -> None:
    _seed_and_build(tmp_path)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    scores = [e["score"] for e in result]
    assert scores == sorted(scores, reverse=True)


def test_rank_returns_empty_when_store_built_but_zero_chunks(tmp_path: Path) -> None:
    """v0.9 痛点 #7 regression — a prior ``codemap embed`` against an empty
    knowledge-base writes chunks.json=[] + vectors.npy with shape (0, D), so
    ``store.is_built`` is True but there's nothing to compare against. The
    hook must short-circuit BEFORE calling ``build_backend()`` (which would
    trigger sentence-transformers import → first-time HuggingFace metadata
    fetch — that hangs on restricted networks even with a valid SOCKS
    proxy).

    If this regresses, the user sees ``codemap recall`` hang silently on
    fresh non-git-repo projects with empty knowledge-base/ + ST installed
    but no model downloaded yet.
    """
    # Seed an empty store: directory + files exist, but chunks.json holds [].
    rebuild_index(tmp_path, _FakeBackend())  # builds with 0 chunks
    # Sanity: the seeded scenario must reproduce the pre-fix state.
    from codemap_semantic_index.store import SemanticStore

    store = SemanticStore(tmp_path)
    assert store.is_built, "test setup: store files must exist"
    assert not store.load_chunks(), "test setup: store must be empty (0 chunks)"

    # build_backend must NEVER be called in this path. If pre-check is
    # bypassed, this patch raises a clear marker error.
    def _explode(_cfg):
        raise AssertionError(
            "build_backend called for an empty store — pre-check regressed; "
            "ST/HF would have been imported and the user would have hung."
        )

    with patch("codemap_semantic_index.recall_hook.build_backend", side_effect=_explode):
        result = recall_hook.rank("anything", tmp_path, base_candidates=[])
    assert result == []


def test_rank_returns_empty_when_include_shared_with_empty_shared_stores(
    tmp_path: Path,
) -> None:
    """Same pre-check logic but for the shared path (FIX-3e). An admin who
    built a shared root against an empty source should not cause every
    member project's recall to hang on first call."""
    proj = tmp_path / "proj"
    shared = tmp_path / "team"
    rebuild_index(proj, _FakeBackend())  # local empty
    rebuild_index(shared, _FakeBackend())  # shared empty

    def _explode(_cfg):
        raise AssertionError("build_backend called when both stores have 0 chunks")

    with patch("codemap_semantic_index.recall_hook.build_backend", side_effect=_explode):
        result = recall_hook.rank(
            "anything",
            proj,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    assert result == []
