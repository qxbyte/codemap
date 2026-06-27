"""Tests for knowledge_schema — the single authority for the 5-category
knowledge contract (FIX-2 / AI-EDS RC-B).

Previously the schema was defined three independent times (task-swarm hand-
rolled dicts, specode-distill markdown templates, recall field constants).
This module is the one place all three reference.
"""

from __future__ import annotations

from codemap_aimemory import knowledge_schema as ks


def test_categories_are_the_five():
    assert ks.CATEGORIES == ("rules", "business", "modules", "cases", "pitfalls")


def test_category_type_mapping():
    assert ks.CATEGORY_TYPE == {
        "rules": "business_rule",
        "business": "business_process",
        "modules": "module_map",
        "cases": "case",
        "pitfalls": "pitfall",
    }


def test_id_prefix_mapping():
    assert ks.ID_PREFIX == {
        "rules": "rule",
        "business": "biz",
        "modules": "mod",
        "cases": "case",
        "pitfalls": "pit",
    }


def test_content_fields_match_recall_expectations():
    # recall.py's --with-content extraction must stay byte-identical, so the
    # schema is the authority recall imports.
    assert ks.CONTENT_FIELDS_BY_CATEGORY["rules"] == (
        "statement",
        "why",
        "trigger_conditions",
        "exceptions",
        "enforcement",
    )
    assert ks.CONTENT_FIELDS_BY_CATEGORY["pitfalls"] == (
        "symptom",
        "root_cause",
        "fix",
        "prevention",
        "affects",
    )
    assert ks.CONTENT_FIELDS_BY_CATEGORY["cases"] == (
        "implementation_summary",
        "key_decisions",
        "bugs_encountered",
        "lessons",
        "review_findings",
        "acceptance_status",
        "changed_files",
    )


def test_common_fields_present():
    for f in (
        "schema_version",
        "knowledge_id",
        "type",
        "version",
        "created_at",
        "updated_at",
        "status",
        "confidence",
    ):
        assert f in ks.COMMON_FIELDS


def test_validate_passes_well_formed_rule():
    kn = {
        "schema_version": "1.0",
        "knowledge_id": "rule-coupon-mutex",
        "type": "business_rule",
        "version": 1,
        "created_at": "2026-06-27",
        "updated_at": "2026-06-27",
        "status": "active",
        "confidence": "high",
        "statement": "优惠券和积分不能同时用",
    }
    assert ks.validate(kn, "rules") == []


def test_validate_flags_type_mismatch():
    kn = {
        "knowledge_id": "rule-x",
        "type": "pitfall",  # wrong for rules
        "version": 1,
        "created_at": "2026-06-27",
        "updated_at": "2026-06-27",
        "status": "active",
        "confidence": "high",
    }
    errs = ks.validate(kn, "rules")
    assert any("type" in e for e in errs)


def test_validate_flags_missing_required():
    kn = {"type": "business_rule"}  # missing knowledge_id / version / dates
    errs = ks.validate(kn, "rules")
    assert any("knowledge_id" in e for e in errs)
    assert any("version" in e for e in errs)


def test_validate_flags_prefix_mismatch():
    kn = {
        "knowledge_id": "pit-wrong-prefix",  # should be rule- for rules
        "type": "business_rule",
        "version": 1,
        "created_at": "2026-06-27",
        "updated_at": "2026-06-27",
        "status": "active",
        "confidence": "high",
    }
    errs = ks.validate(kn, "rules")
    assert any("prefix" in e or "knowledge_id" in e for e in errs)


def test_validate_unknown_category():
    errs = ks.validate({"knowledge_id": "x-1"}, "bogus")
    assert any("category" in e for e in errs)
