"""Tests for FIX-3e — opt-in cross-project shared semantic recall.

When ``include_shared=True`` and shared roots are configured (typically
via ``~/.config/codemap/recall.yaml``), the hook ALSO scans the shared
roots' ``_semantic/`` stores. Hits are labelled ``source: shared`` and
demoted; the local rule always wins on ``knowledge_id`` collision.

Model-space consistency is hard-required: a shared store whose
``model_id`` ≠ the local backend's is silently skipped with a stderr
warning — never mixed (would compare vectors from different spaces).
"""

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


class _OtherFakeBackend(_FakeBackend):
    """Same vector space dim but a *different* model_id, to trigger
    ModelMismatch on the shared store."""

    model_id = "local:huggingface:different-model"


def _seed_local(project_root: Path) -> None:
    rules = project_root / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-local-only.md").write_text(
        "# local rule\n\n## why\n\nproject specific coupon constraint\n",
        encoding="utf-8",
    )
    rebuild_index(project_root, _FakeBackend())


def _seed_shared(shared_root: Path) -> None:
    rules = shared_root / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-shared.md").write_text(
        "# shared rule\n\n## why\n\nteam wide coupon constraint\n",
        encoding="utf-8",
    )
    rebuild_index(shared_root, _FakeBackend())


def test_default_off_does_not_scan_shared(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    _seed_shared(shared)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("coupon", project, base_candidates=[])
    ids = {e["knowledge_id"] for e in result}
    assert "rule-shared" not in ids
    assert all(e.get("source", "local") == "local" for e in result)


def test_include_shared_surfaces_shared_with_label(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    _seed_shared(shared)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank(
            "coupon",
            project,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    by_id = {e["knowledge_id"]: e for e in result}
    assert "rule-local-only" in by_id
    assert "rule-shared" in by_id
    assert by_id["rule-local-only"]["source"] == "local"
    assert by_id["rule-shared"]["source"] == "shared"


def test_shared_hit_is_demoted(tmp_path: Path) -> None:
    """For the same query, shared hit's score is multiplied by the demotion
    factor so equal-overlap local always wins."""
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    # Identical content in both — same raw similarity, but local should rank
    # strictly higher due to the demotion factor.
    (project / "knowledge-base" / "rules").mkdir(parents=True)
    (shared / "knowledge-base" / "rules").mkdir(parents=True)
    same = "# x\n\n## why\n\ncoupon rule\n"
    (project / "knowledge-base" / "rules" / "rule-local.md").write_text(same, encoding="utf-8")
    (shared / "knowledge-base" / "rules" / "rule-shared.md").write_text(same, encoding="utf-8")
    rebuild_index(project, _FakeBackend())
    rebuild_index(shared, _FakeBackend())

    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank(
            "coupon",
            project,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    by_id = {e["knowledge_id"]: e for e in result}
    assert by_id["rule-local"]["score"] > by_id["rule-shared"]["score"]


def test_mismatched_model_id_skips_shared(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    # Shared store built with a different model → its model_id.txt holds
    # a different identity; loading should refuse to mix vector spaces.
    rules = shared / "knowledge-base" / "rules"
    rules.mkdir(parents=True)
    (rules / "rule-shared.md").write_text("# x\n\n## why\n\nshared\n", encoding="utf-8")
    rebuild_index(shared, _OtherFakeBackend())

    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank(
            "coupon",
            project,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    ids = {e["knowledge_id"] for e in result}
    assert "rule-shared" not in ids  # silently dropped


def test_unbuilt_shared_root_is_skipped(tmp_path: Path) -> None:
    """A shared root path that exists but has no _semantic/ is not a crash."""
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    shared.mkdir()
    _seed_local(project)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank(
            "coupon",
            project,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    ids = {e["knowledge_id"] for e in result}
    assert "rule-local-only" in ids  # local still works


def test_id_collision_local_wins(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    (project / "knowledge-base" / "rules").mkdir(parents=True)
    (shared / "knowledge-base" / "rules").mkdir(parents=True)
    (project / "knowledge-base" / "rules" / "rule-collision.md").write_text(
        "# x\n\n## why\n\nLOCAL coupon\n", encoding="utf-8"
    )
    (shared / "knowledge-base" / "rules" / "rule-collision.md").write_text(
        "# x\n\n## why\n\nSHARED coupon\n", encoding="utf-8"
    )
    rebuild_index(project, _FakeBackend())
    rebuild_index(shared, _FakeBackend())

    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank(
            "coupon",
            project,
            base_candidates=[],
            include_shared=True,
            shared_roots=[shared],
        )
    hits = [e for e in result if e["knowledge_id"] == "rule-collision"]
    assert len(hits) == 1
    assert hits[0]["source"] == "local"


def test_old_signature_still_callable_back_compat(tmp_path: Path) -> None:
    """A caller from aimemory < 0.4.4 (no shared kwargs) keeps working."""
    _seed_local(tmp_path)
    with patch(
        "codemap_semantic_index.recall_hook.build_backend",
        return_value=_FakeBackend(),
    ):
        result = recall_hook.rank("coupon", tmp_path, base_candidates=[])
    assert isinstance(result, list)
