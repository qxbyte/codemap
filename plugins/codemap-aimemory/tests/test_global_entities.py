"""Tests for the global entity index aggregator (P1-2)."""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.global_entities import build_global_entities


def _write_knowledge(out_dir: Path, subdir: str, name: str, data: dict) -> None:
    target_dir = out_dir / "knowledge" / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{name}.yml").write_text(yaml.safe_dump(data, allow_unicode=True))


# ---------- empty / fresh project ----------


def test_no_knowledge_dir_returns_code_only_entities(tmp_path: Path) -> None:
    result = build_global_entities(tmp_path, ["fn-calc", "cls-Foo", "tbl-orders"])
    by_id = {e["id"]: e for e in result["entities"]}
    assert set(by_id.keys()) == {"fn-calc", "cls-Foo", "tbl-orders"}
    for ent in by_id.values():
        assert ent["source"] == "code"
        assert ent["knowledge_refs"] == []
    assert result["counts"]["code_only"] == 3
    assert result["counts"]["both"] == 0
    assert result["counts"]["knowledge_only"] == 0


def test_no_code_and_no_knowledge_returns_empty(tmp_path: Path) -> None:
    result = build_global_entities(tmp_path, [])
    assert result["entities"] == []
    assert result["counts"]["total"] == 0


def test_empty_knowledge_subdirs_tolerated(tmp_path: Path) -> None:
    (tmp_path / "knowledge" / "rules").mkdir(parents=True)
    (tmp_path / "knowledge" / "cases").mkdir(parents=True)
    result = build_global_entities(tmp_path, ["fn-only"])
    assert {e["id"] for e in result["entities"]} == {"fn-only"}
    assert result["entities"][0]["source"] == "code"


# ---------- knowledge → code linking ----------


def test_related_code_entity_links_to_code(tmp_path: Path) -> None:
    _write_knowledge(
        tmp_path,
        "rules",
        "rule-coupon-mutex",
        {
            "knowledge_id": "rule-coupon-mutex",
            "related_code": [
                {"entity": "fn-calc", "file": "src/order.py"},
                {"entity": "fn-validate"},
            ],
        },
    )
    result = build_global_entities(tmp_path, ["fn-calc"])
    by_id = {e["id"]: e for e in result["entities"]}
    # fn-calc exists in both code and knowledge
    assert by_id["fn-calc"]["source"] == "both"
    assert by_id["fn-calc"]["knowledge_refs"] == ["rule-coupon-mutex"]
    # fn-validate only appears in knowledge
    assert by_id["fn-validate"]["source"] == "knowledge"
    assert by_id["fn-validate"]["knowledge_refs"] == ["rule-coupon-mutex"]


def test_related_knowledge_cross_references_counted(tmp_path: Path) -> None:
    _write_knowledge(
        tmp_path,
        "business",
        "biz-checkout",
        {
            "knowledge_id": "biz-checkout",
            "related_knowledge": ["rule-coupon-mutex", "mod-pricing"],
        },
    )
    result = build_global_entities(tmp_path, [])
    by_id = {e["id"]: e for e in result["entities"]}
    assert "rule-coupon-mutex" in by_id
    assert by_id["rule-coupon-mutex"]["knowledge_refs"] == ["biz-checkout"]
    assert by_id["mod-pricing"]["knowledge_refs"] == ["biz-checkout"]


def test_multiple_knowledge_files_referencing_same_entity_merged(tmp_path: Path) -> None:
    _write_knowledge(
        tmp_path,
        "rules",
        "rule-a",
        {"knowledge_id": "rule-a", "related_code": [{"entity": "tbl-orders"}]},
    )
    _write_knowledge(
        tmp_path,
        "cases",
        "case-001",
        {"knowledge_id": "case-001", "related_code": [{"entity": "tbl-orders"}]},
    )
    result = build_global_entities(tmp_path, ["tbl-orders"])
    by_id = {e["id"]: e for e in result["entities"]}
    assert sorted(by_id["tbl-orders"]["knowledge_refs"]) == ["case-001", "rule-a"]


def test_pitfall_affects_entity_ids_only_not_file_paths(tmp_path: Path) -> None:
    _write_knowledge(
        tmp_path,
        "pitfalls",
        "pit-null-amount",
        {
            "knowledge_id": "pit-null-amount",
            "affects": [
                "fn-calculate-price",  # entity_id → registered
                "src/order/query.py",  # file path → skipped
            ],
        },
    )
    result = build_global_entities(tmp_path, [])
    by_id = {e["id"]: e for e in result["entities"]}
    assert "fn-calculate-price" in by_id
    assert "src/order/query.py" not in by_id


# ---------- robustness ----------


def test_malformed_yml_skipped_without_crash(tmp_path: Path) -> None:
    (tmp_path / "knowledge" / "rules").mkdir(parents=True)
    (tmp_path / "knowledge" / "rules" / "broken.yml").write_text("not: valid: ::: yaml")
    _write_knowledge(
        tmp_path,
        "rules",
        "rule-good",
        {"knowledge_id": "rule-good", "related_code": [{"entity": "fn-x"}]},
    )
    result = build_global_entities(tmp_path, [])
    by_id = {e["id"]: e for e in result["entities"]}
    # broken.yml was silently skipped; rule-good's reference still landed
    assert "fn-x" in by_id
    assert by_id["fn-x"]["knowledge_refs"] == ["rule-good"]


def test_knowledge_yml_falls_back_to_stem_when_no_knowledge_id(tmp_path: Path) -> None:
    """A hand-written knowledge yml that forgot ``knowledge_id``
    still contributes to the index, keyed by filename."""
    target_dir = tmp_path / "knowledge" / "rules"
    target_dir.mkdir(parents=True)
    (target_dir / "rule-no-id.yml").write_text(
        yaml.safe_dump({"related_code": [{"entity": "fn-z"}]}, allow_unicode=True)
    )
    result = build_global_entities(tmp_path, [])
    by_id = {e["id"]: e for e in result["entities"]}
    assert by_id["fn-z"]["knowledge_refs"] == ["rule-no-id"]


# ---------- type inference ----------


def test_type_inferred_from_id_prefix(tmp_path: Path) -> None:
    result = build_global_entities(
        tmp_path,
        ["fn-a", "cls-B", "tbl-c", "mod-d", "unknown-e"],
    )
    by_id = {e["id"]: e["type"] for e in result["entities"]}
    assert by_id["fn-a"] == "function"
    assert by_id["cls-B"] == "class"
    assert by_id["tbl-c"] == "table"
    assert by_id["mod-d"] == "module"
    assert by_id["unknown-e"] == "unknown"


def test_knowledge_only_entity_types_inferred(tmp_path: Path) -> None:
    """rule-/biz-/case-/pit- prefixes come from spec-distill only."""
    _write_knowledge(
        tmp_path,
        "business",
        "biz-checkout",
        {
            "knowledge_id": "biz-checkout",
            "related_knowledge": ["rule-x", "case-001", "pit-y"],
        },
    )
    result = build_global_entities(tmp_path, [])
    by_id = {e["id"]: e["type"] for e in result["entities"]}
    assert by_id["rule-x"] == "rule"
    assert by_id["case-001"] == "case"
    assert by_id["pit-y"] == "pitfall"


# ---------- counts ----------


def test_counts_partition_correctly(tmp_path: Path) -> None:
    _write_knowledge(
        tmp_path,
        "rules",
        "rule-x",
        {
            "knowledge_id": "rule-x",
            "related_code": [{"entity": "fn-both"}, {"entity": "fn-kn-only"}],
        },
    )
    code_ids = ["fn-both", "fn-code-only"]
    result = build_global_entities(tmp_path, code_ids)
    counts = result["counts"]
    assert counts["total"] == 4  # fn-both, fn-code-only, fn-kn-only, rule-x
    assert counts["both"] == 1  # fn-both
    assert counts["code_only"] == 1  # fn-code-only
    assert counts["knowledge_only"] == 2  # fn-kn-only, rule-x


def test_generated_at_is_iso_date(tmp_path: Path) -> None:
    import re

    result = build_global_entities(tmp_path, [])
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result["generated_at"])
