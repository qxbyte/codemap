"""Tests for FIX-3c — entity exact recall hook.

Goal: when the query names a specific table / class / api-path / FQN,
those knowledge entries whose ``related_code[].entity`` list precisely
contains that entity should be ranked first — independent of, and
alongside, the token-bigram path.

Registered via the ``codemap.recall_hooks`` entry-point so it composes
through the existing RRF fuser; no surgery on recall.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.entity_exact_hook import rank


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _seed(project_root: Path) -> None:
    base = project_root / ".ai-memory" / "knowledge"
    _write_yaml(
        base / "rules" / "rule-order-mutex.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "rule-order-mutex",
            "type": "business_rule",
            "version": 1,
            "created_at": "2026-06-27",
            "updated_at": "2026-06-27",
            "status": "active",
            "confidence": "high",
            "statement": "coupon vs points mutex",
            "related_code": [
                {"entity": "sf_order", "kind": "table"},
                {"entity": "com.helloshop.order.OrderController", "kind": "class"},
            ],
        },
    )
    _write_yaml(
        base / "cases" / "case-batch-address.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "case-batch-address",
            "type": "case",
            "version": 1,
            "created_at": "2026-06-27",
            "updated_at": "2026-06-27",
            "status": "active",
            "confidence": "high",
            "implementation_summary": "batch update order address",
            "related_code": [
                {"entity": "/api/order/batch-address", "kind": "api"},
                {"entity": "OrderController", "kind": "class"},
            ],
        },
    )
    _write_yaml(
        base / "pitfalls" / "pit-unrelated.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "pit-unrelated",
            "type": "pitfall",
            "version": 1,
            "created_at": "2026-06-27",
            "updated_at": "2026-06-27",
            "status": "active",
            "confidence": "high",
            "symptom": "totally unrelated",
            "related_code": [{"entity": "PaymentService", "kind": "class"}],
        },
    )


def test_precise_table_name_hits_only_matching_knowledge(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = rank(query="改 sf_order 的字段", project_root=tmp_path, base_candidates=[])
    ids = [r["knowledge_id"] for r in result]
    assert "rule-order-mutex" in ids
    assert "pit-unrelated" not in ids


def test_api_path_match(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = rank(
        query="hit POST /api/order/batch-address", project_root=tmp_path, base_candidates=[]
    )
    ids = [r["knowledge_id"] for r in result]
    assert "case-batch-address" in ids


def test_camelcase_class_match(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = rank(query="touch OrderController logic", project_root=tmp_path, base_candidates=[])
    ids = [r["knowledge_id"] for r in result]
    # Both rule-order-mutex (com.helloshop.order.OrderController) and
    # case-batch-address (OrderController) should match.
    assert "case-batch-address" in ids
    # FQN form should also match its CamelCase suffix:
    assert "rule-order-mutex" in ids


def test_more_matches_rank_higher(tmp_path: Path) -> None:
    _seed(tmp_path)
    # case-batch-address has both /api/order/batch-address AND OrderController matched
    # rule-order-mutex has only OrderController matched (via its FQN)
    result = rank(
        query="改 /api/order/batch-address on OrderController",
        project_root=tmp_path,
        base_candidates=[],
    )
    ids = [r["knowledge_id"] for r in result]
    assert ids.index("case-batch-address") < ids.index("rule-order-mutex")


def test_no_entities_returns_empty(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = rank(query="改地址", project_root=tmp_path, base_candidates=[])
    assert result == []


def test_no_knowledge_dir_returns_empty(tmp_path: Path) -> None:
    result = rank(query="touch OrderController", project_root=tmp_path, base_candidates=[])
    assert result == []


def test_each_hit_has_required_shape(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = rank(query="sf_order", project_root=tmp_path, base_candidates=[])
    assert result
    hit = result[0]
    # Hook contract: must carry knowledge_id; SHOULD carry category /
    # type / title for RRF metadata mirroring.
    assert hit["knowledge_id"] == "rule-order-mutex"
    assert hit["category"] == "rules"
    assert hit["type"] == "business_rule"
    assert "matched_entities" in hit
    assert "sf_order" in hit["matched_entities"]


def test_does_not_double_count_same_entity(tmp_path: Path) -> None:
    """Two `related_code` entries both naming the same entity should count
    once, so match-count ordering is stable."""
    base = tmp_path / ".ai-memory" / "knowledge"
    _write_yaml(
        base / "rules" / "rule-dup.yml",
        {
            "schema_version": "1.0",
            "knowledge_id": "rule-dup",
            "type": "business_rule",
            "version": 1,
            "created_at": "2026-06-27",
            "updated_at": "2026-06-27",
            "status": "active",
            "confidence": "high",
            "statement": "x",
            "related_code": [
                {"entity": "sf_order", "kind": "table"},
                {"entity": "sf_order", "kind": "table"},  # dup
            ],
        },
    )
    result = rank(query="sf_order", project_root=tmp_path, base_candidates=[])
    assert len(result) == 1
    assert result[0]["matched_entities"] == ["sf_order"]
