"""Tests for FIX-3d — opt-in cross-project shared knowledge in recall.

Shared roots are knowledge directories outside the current project_root
that team members opt into via ``--include-shared`` (or CLI default).
Hits get labelled ``source: shared`` and are demoted vs ``source: local``
hits so a local rule always wins ties.

Project-root isolation (the v3 design choice that fixed ISSUE-4 cross-
project混淆) stays intact by default — shared only kicks in when the
user explicitly asks for it.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from codemap_aimemory.recall import recall

TODAY = datetime.date(2026, 6, 27)
TODAY_STR = "2026-06-27"


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _seed_local(project_root: Path) -> None:
    base = project_root / ".ai-memory" / "knowledge"
    _write_yaml(
        base / "rules" / "rule-local-coupon.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "rule-local-coupon",
            "type": "business_rule",
            "version": 1,
            "created_at": TODAY_STR,
            "updated_at": TODAY_STR,
            "status": "active",
            "confidence": "high",
            "statement": "coupon points mutex local",
        },
    )


def _seed_shared(shared_root: Path) -> None:
    base = shared_root / ".ai-memory" / "knowledge"
    _write_yaml(
        base / "rules" / "rule-shared-coupon.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "rule-shared-coupon",
            "type": "business_rule",
            "version": 1,
            "created_at": TODAY_STR,
            "updated_at": TODAY_STR,
            "status": "active",
            "confidence": "high",
            "statement": "coupon team-wide rule shared",
        },
    )


def test_include_shared_default_off_is_back_compat(tmp_path: Path) -> None:
    """No flag = no shared scan, even if shared_roots is configured."""
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    _seed_shared(shared)
    result = recall(query="coupon", project_root=project, today=TODAY, shared_roots=[shared])
    ids = [c["knowledge_id"] for c in result["knowledge"]]
    assert "rule-local-coupon" in ids
    assert "rule-shared-coupon" not in ids
    assert all(c.get("source", "local") == "local" for c in result["knowledge"])


def test_include_shared_surfaces_shared_with_label(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    _seed_shared(shared)
    result = recall(
        query="coupon",
        project_root=project,
        today=TODAY,
        shared_roots=[shared],
        include_shared=True,
    )
    by_id = {c["knowledge_id"]: c for c in result["knowledge"]}
    assert "rule-local-coupon" in by_id
    assert "rule-shared-coupon" in by_id
    assert by_id["rule-local-coupon"]["source"] == "local"
    assert by_id["rule-shared-coupon"]["source"] == "shared"


def test_shared_is_demoted_below_equal_local(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    _seed_local(project)
    _seed_shared(shared)
    result = recall(
        query="coupon",
        project_root=project,
        today=TODAY,
        shared_roots=[shared],
        include_shared=True,
    )
    ids = [c["knowledge_id"] for c in result["knowledge"]]
    assert ids.index("rule-local-coupon") < ids.index("rule-shared-coupon")
    # And the shared entry's ranked_score is strictly less for the same
    # underlying token overlap.
    by_id = {c["knowledge_id"]: c for c in result["knowledge"]}
    assert by_id["rule-shared-coupon"]["ranked_score"] < by_id["rule-local-coupon"]["ranked_score"]


def test_local_wins_on_id_collision(tmp_path: Path) -> None:
    """Same knowledge_id in both roots → local entry wins, shared is dropped
    (no double-count, no flapping source labels)."""
    project = tmp_path / "proj"
    shared = tmp_path / "team"
    # Same knowledge_id deliberately.
    local_payload = {
        "schema_version": "1.0",
        "knowledge_id": "rule-coupon-mutex",
        "type": "business_rule",
        "version": 1,
        "created_at": TODAY_STR,
        "updated_at": TODAY_STR,
        "status": "active",
        "confidence": "high",
        "statement": "LOCAL coupon rule",
    }
    shared_payload = {**local_payload, "statement": "SHARED coupon rule"}
    _write_yaml(project / ".ai-memory/knowledge/rules/rule-coupon-mutex.yml", local_payload)
    _write_yaml(shared / ".ai-memory/knowledge/rules/rule-coupon-mutex.yml", shared_payload)

    result = recall(
        query="coupon",
        project_root=project,
        today=TODAY,
        shared_roots=[shared],
        include_shared=True,
    )
    hits = [c for c in result["knowledge"] if c["knowledge_id"] == "rule-coupon-mutex"]
    assert len(hits) == 1
    assert hits[0]["source"] == "local"
    assert "LOCAL" in (hits[0].get("title") or hits[0].get("summary") or "")


def test_unreachable_shared_root_is_skipped(tmp_path: Path) -> None:
    """A configured shared root that does not exist (unmounted drive, typo)
    must not crash recall — it skips with a warning and continues."""
    project = tmp_path / "proj"
    missing = tmp_path / "does-not-exist"
    _seed_local(project)
    result = recall(
        query="coupon",
        project_root=project,
        today=TODAY,
        shared_roots=[missing],
        include_shared=True,
    )
    ids = [c["knowledge_id"] for c in result["knowledge"]]
    assert "rule-local-coupon" in ids
