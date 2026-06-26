"""Tests for the recall hook discovery + RRF fusion (P1-3 PR1).

These tests stub the ``codemap.recall_hooks`` entry-point loader to
inject controlled rankers, then verify:

- discovery + filtering (non-callable / load-failure skipped)
- candidate union with hook-introduced ids
- RRF math vs hand-computed expectations
- back-compat: no hooks → token-only output unchanged
- error containment: a raising hook doesn't take recall down
- final ``ranked_score = rrf_score * freshness_score`` preserved
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from codemap_aimemory.recall import RRF_K, recall


def _seed_knowledge(tmp_path: Path) -> None:
    """Seed three rules where only `rule-coupon-mutex` matches the 'coupon'
    query via token recall. The other two are introduced only by hooks
    so RRF math has clean inputs."""
    base = tmp_path / ".ai-memory" / "knowledge" / "rules"
    base.mkdir(parents=True)
    items = {
        "rule-coupon-mutex": {
            "title": "coupon mutex",
            "statement": "coupon and points cannot stack",
        },
        "rule-points-cap": {
            "title": "points cap",
            "statement": "points capped at one thousand per order",
        },
        "rule-vip-perk": {
            "title": "vip perk",
            "statement": "vip users get free shipping",
        },
    }
    for kid, fields in items.items():
        (base / f"{kid}.yml").write_text(
            yaml.safe_dump(
                {
                    "knowledge_id": kid,
                    "type": "business_rule",
                    "updated_at": "2026-06-27",
                    **fields,
                },
                allow_unicode=True,
            )
        )


def _stub_hooks(*hooks: tuple[str, Any]) -> Any:
    """Patch ``_load_recall_hooks`` to return the given (name, callable) tuples."""
    return patch("codemap_aimemory.recall._load_recall_hooks", lambda: list(hooks))


# ---------- back-compat ----------


def test_no_hooks_means_token_only_path(tmp_path: Path) -> None:
    """With no hooks discovered, output is identical to 0.4.0 behaviour
    (ranked_score = score * freshness, no rrf_score / ranked_by fields)."""
    _seed_knowledge(tmp_path)
    with _stub_hooks():
        result = recall("coupon", tmp_path)
    item = result["knowledge"][0]
    assert "rrf_score" not in item
    assert "ranked_by" not in item
    assert "ranked_score" in item


# ---------- single hook ----------


def test_single_hook_adds_rrf_and_ranked_by(tmp_path: Path) -> None:
    _seed_knowledge(tmp_path)

    def fake_hook(query: str, project_root: Path, base_candidates: list[dict]) -> list[dict]:
        # hook ranks a completely separate id at rank 1
        return [
            {
                "knowledge_id": "rule-vip-perk",
                "type": "business_rule",
                "category": "rules",
                "title": "vip rule",
                "summary": "from semantic",
                "file": ".ai-memory/knowledge/rules/rule-vip-perk.yml",
                "score": 0.99,
                "freshness_score": 1.0,
                "stale": False,
            },
        ]

    with _stub_hooks(("semantic", fake_hook)):
        result = recall("coupon", tmp_path)

    ids = [k["knowledge_id"] for k in result["knowledge"]]
    # hook introduced rule-vip-perk which token-recall didn't hit
    assert "rule-vip-perk" in ids
    vip = next(k for k in result["knowledge"] if k["knowledge_id"] == "rule-vip-perk")
    assert "rrf_score" in vip
    assert vip["ranked_by"] == ["semantic"]


# ---------- candidate union + RRF math ----------


def test_rrf_sum_is_correct_for_overlapping_id(tmp_path: Path) -> None:
    """An id appearing in both rankings should accumulate RRF contributions
    from both. Hand-computed: token rank 1 + semantic rank 1 = 2/(60+1)."""
    _seed_knowledge(tmp_path)

    def hook_with_same_id(query, project_root, base_candidates):
        return [
            {
                "knowledge_id": "rule-coupon-mutex",  # also in token recall (matches 'coupon')
                "type": "business_rule",
                "category": "rules",
                "title": "title for rule-coupon-mutex",
                "summary": "from semantic",
                "file": ".ai-memory/knowledge/rules/rule-coupon-mutex.yml",
                "score": 0.99,
                "freshness_score": 1.0,
                "stale": False,
            },
        ]

    with _stub_hooks(("semantic", hook_with_same_id)):
        result = recall("coupon", tmp_path)

    mutex = next(k for k in result["knowledge"] if k["knowledge_id"] == "rule-coupon-mutex")
    # token rank 1 + semantic rank 1 → both contribute 1/(60+1)
    expected_rrf = round(2.0 / (RRF_K + 1), 4)
    assert mutex["rrf_score"] == expected_rrf
    assert sorted(mutex["ranked_by"]) == ["semantic", "token"]


def test_ranked_score_includes_freshness_multiplier(tmp_path: Path) -> None:
    """``ranked_score = rrf_score * freshness_score`` preserved end-to-end."""
    base = tmp_path / ".ai-memory" / "knowledge" / "rules"
    base.mkdir(parents=True)
    # Two-year-old knowledge → very low freshness
    (base / "rule-stale.yml").write_text(
        yaml.safe_dump(
            {
                "knowledge_id": "rule-stale",
                "type": "business_rule",
                "title": "stale rule",
                "statement": "coupon stale",
                "updated_at": "2024-06-27",
            },
            allow_unicode=True,
        )
    )

    def hook_ranks_stale(query, project_root, base_candidates):
        return [
            {
                "knowledge_id": "rule-stale",
                "score": 0.99,
                "freshness_score": 1.0,
                "type": "business_rule",
                "category": "rules",
                "title": "stale rule",
                "summary": "",
                "file": ".ai-memory/knowledge/rules/rule-stale.yml",
                "stale": False,
            },
        ]

    with _stub_hooks(("semantic", hook_ranks_stale)):
        result = recall("coupon", tmp_path)

    item = result["knowledge"][0]
    # token-side metadata wins (first-seen), so freshness should be low
    assert item["freshness_score"] < 0.2
    # rrf_score * freshness < rrf_score
    assert item["ranked_score"] < item["rrf_score"]


# ---------- error containment ----------


def test_hook_that_raises_does_not_break_recall(tmp_path: Path) -> None:
    _seed_knowledge(tmp_path)

    def bad_hook(query, project_root, base_candidates):
        raise RuntimeError("boom")

    with _stub_hooks(("bad", bad_hook)), pytest.warns(UserWarning, match="raised at call"):
        result = recall("coupon", tmp_path)
    # token recall still works
    assert any(k["knowledge_id"] == "rule-coupon-mutex" for k in result["knowledge"])


def test_hook_returning_garbage_is_filtered(tmp_path: Path) -> None:
    _seed_knowledge(tmp_path)

    def garbage_hook(query, project_root, base_candidates):
        return [
            {"not_knowledge_id": "rule-x"},  # missing knowledge_id → dropped
            42,  # not a dict → dropped
            {
                "knowledge_id": "rule-vip-perk",
                "score": 0.5,
                "freshness_score": 1.0,
                "type": "business_rule",
                "category": "rules",
                "title": "vip",
                "summary": "",
                "file": ".ai-memory/knowledge/rules/rule-vip-perk.yml",
                "stale": False,
            },
        ]

    with _stub_hooks(("garbage", garbage_hook)):
        result = recall("coupon", tmp_path)
    ids = {k["knowledge_id"] for k in result["knowledge"]}
    assert "rule-vip-perk" in ids  # the valid one made it through


def test_hook_returning_non_iterable_is_warned(tmp_path: Path) -> None:
    _seed_knowledge(tmp_path)

    def bad_shape(query, project_root, base_candidates):
        return 42  # neither list nor iterable

    with _stub_hooks(("bad", bad_shape)), pytest.warns(UserWarning, match="non-iterable"):
        result = recall("coupon", tmp_path)
    # token recall result intact
    assert any(k["knowledge_id"] == "rule-coupon-mutex" for k in result["knowledge"])


# ---------- discovery filtering ----------


def test_non_callable_hook_skipped() -> None:
    """A non-callable entry-point object should be skipped with a warning,
    without crashing the loader."""
    from codemap_aimemory import recall as recall_mod

    class _FakeEP:
        name = "broken"

        def load(self):
            return "i_am_a_string_not_callable"

    with patch("codemap_aimemory.recall._md.entry_points", lambda group: [_FakeEP()]):
        with pytest.warns(UserWarning, match="not callable"):
            loaded = recall_mod._load_recall_hooks()
        assert loaded == []


def test_hook_load_failure_skipped() -> None:
    from codemap_aimemory import recall as recall_mod

    class _FakeEP:
        name = "broken"

        def load(self):
            raise ImportError("missing dep")

    with patch("codemap_aimemory.recall._md.entry_points", lambda group: [_FakeEP()]):
        with pytest.warns(UserWarning, match="failed to load"):
            loaded = recall_mod._load_recall_hooks()
        assert loaded == []


# ---------- multi-hook ----------


def test_two_hooks_both_contribute_to_rrf(tmp_path: Path) -> None:
    _seed_knowledge(tmp_path)

    def hook_a(query, project_root, base_candidates):
        return [
            {
                "knowledge_id": "rule-vip-perk",
                "score": 0.9,
                "freshness_score": 1.0,
                "type": "business_rule",
                "category": "rules",
                "title": "vip",
                "summary": "from a",
                "file": ".ai-memory/knowledge/rules/rule-vip-perk.yml",
                "stale": False,
            },
        ]

    def hook_b(query, project_root, base_candidates):
        return [
            {
                "knowledge_id": "rule-vip-perk",
                "score": 0.85,
                "freshness_score": 1.0,
                "type": "business_rule",
                "category": "rules",
                "title": "vip",
                "summary": "from b",
                "file": ".ai-memory/knowledge/rules/rule-vip-perk.yml",
                "stale": False,
            },
        ]

    with _stub_hooks(("a", hook_a), ("b", hook_b)):
        result = recall("coupon", tmp_path)
    vip = next(k for k in result["knowledge"] if k["knowledge_id"] == "rule-vip-perk")
    # Both hooks ranked it at #1, neither token did → 2 contributions
    expected_rrf = round(2.0 / (RRF_K + 1), 4)
    assert vip["rrf_score"] == expected_rrf
    assert sorted(vip["ranked_by"]) == ["a", "b"]
