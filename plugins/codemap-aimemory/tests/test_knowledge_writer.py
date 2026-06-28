"""Tests for knowledge_writer — the single deterministic writer of
.ai-memory/knowledge/*.yml + knowledge-base/*.md (FIX-2).

LLM (specode-distill) and task-swarm both feed a *content payload*; this
module owns everything deterministic: id derivation, schema_version / date
stamping, atomic dual write (yml + md), same-id merge, and red-line checks
(/Volumes mount). The md *body* is authored upstream (方案A) and preserved
verbatim; only the frontmatter is machine-rendered.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import yaml
from codemap_aimemory.knowledge_writer import write_knowledge

TODAY = datetime.date(2026, 6, 27)


def _read_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".ai-memory").mkdir()
    return tmp_path


# ---------- create ----------


def test_create_rule_writes_yml_and_md(project: Path):
    res = write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-coupon-mutex",
            "fields": {"statement": "优惠券和积分不能同时用", "why": "防止亏损"},
            "md_body": "## 规则\n\n散文正文 with ascii\n",
        },
        today=TODAY,
    )
    assert res["errors"] == []
    assert res["action"] == "created"
    yml_path = project / ".ai-memory/knowledge/rules/rule-coupon-mutex.yml"
    md_path = project / "knowledge-base/rules/rule-coupon-mutex.md"
    assert yml_path.is_file()
    assert md_path.is_file()
    kn = _read_yaml(yml_path)
    assert kn["knowledge_id"] == "rule-coupon-mutex"
    assert kn["type"] == "business_rule"
    assert kn["version"] == 1
    assert kn["created_at"] == "2026-06-27"
    assert kn["updated_at"] == "2026-06-27"
    assert kn["schema_version"] == "1.0"
    assert kn["statement"] == "优惠券和积分不能同时用"


def test_md_body_preserved_verbatim(project: Path):
    body = "## 一句话规则\n\n同一订单优惠券与积分互斥。\n\n```\nascii flow\n```\n"
    write_knowledge(
        project,
        "rules",
        {"knowledge_id": "rule-x", "fields": {"statement": "s"}, "md_body": body},
        today=TODAY,
    )
    md = (project / "knowledge-base/rules/rule-x.md").read_text(encoding="utf-8")
    assert body.strip() in md
    assert md.startswith("---\n")  # frontmatter present
    assert "knowledge_id: rule-x" in md


def test_minimal_md_rendered_when_no_body(project: Path):
    write_knowledge(
        project,
        "pitfalls",
        {
            "signature": "amount-null-npe",
            "fields": {"symptom": "NPE on BigDecimal.add", "fix": "Optional.ofNullable"},
        },
        today=TODAY,
    )
    md = (project / "knowledge-base/pitfalls/pit-amount-null-npe.md").read_text(encoding="utf-8")
    assert "NPE on BigDecimal.add" in md  # fields surfaced even without LLM body


# ---------- id derivation ----------


def test_case_id_derived_from_spec_id(project: Path):
    res = write_knowledge(
        project,
        "cases",
        {"spec_id": "REQ-001", "fields": {"implementation_summary": "did the thing"}},
        today=TODAY,
    )
    assert res["knowledge_id"] == "case-req-001"
    assert (project / ".ai-memory/knowledge/cases/case-req-001.yml").is_file()


def test_pit_id_derived_from_signature(project: Path):
    res = write_knowledge(
        project,
        "pitfalls",
        {"signature": "BigDecimal NPE", "fields": {"symptom": "x"}},
        today=TODAY,
    )
    assert res["knowledge_id"] == "pit-bigdecimal-npe"


def test_rule_id_derived_from_title_when_no_id(project: Path):
    res = write_knowledge(
        project,
        "rules",
        {"title": "Coupon Points Mutex", "fields": {"statement": "x"}},
        today=TODAY,
    )
    assert res["knowledge_id"] == "rule-coupon-points-mutex"


# ---------- merge / supersede ----------


def test_case_supersede_overwrites_and_bumps_version(project: Path):
    write_knowledge(
        project,
        "cases",
        {"spec_id": "REQ-001", "fields": {"implementation_summary": "v1"}},
        today=datetime.date(2026, 6, 1),
    )
    res = write_knowledge(
        project,
        "cases",
        {"spec_id": "REQ-001", "fields": {"implementation_summary": "v2 rewritten"}},
        today=TODAY,
    )
    assert res["action"] == "superseded"
    kn = _read_yaml(project / ".ai-memory/knowledge/cases/case-req-001.yml")
    assert kn["version"] == 2
    assert kn["implementation_summary"] == "v2 rewritten"
    assert kn["created_at"] == "2026-06-01"  # original creation preserved
    assert kn["updated_at"] == "2026-06-27"


def test_rule_merge_is_append_only(project: Path):
    write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-x",
            "spec_id": "REQ-001",
            "fields": {"statement": "original statement", "related_requirements": ["REQ-001"]},
        },
        today=datetime.date(2026, 6, 1),
    )
    res = write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-x",
            "spec_id": "REQ-002",
            "fields": {"statement": "should NOT overwrite", "related_requirements": ["REQ-002"]},
        },
        today=TODAY,
    )
    assert res["action"] == "merged"
    kn = _read_yaml(project / ".ai-memory/knowledge/rules/rule-x.yml")
    assert kn["version"] == 2
    assert kn["statement"] == "original statement"  # structural field preserved
    assert set(kn["related_requirements"]) == {"REQ-001", "REQ-002"}  # appended
    assert kn["created_at"] == "2026-06-01"


def test_rule_merge_backfills_blank_structural_fields(project: Path):
    """0.4.9: a follow-up write can fill in *blank* structural fields without
    overwriting already-populated ones. Closes the round-2/3 rule-body-loss
    bug where the first write only stamped frontmatter, leaving structural
    fields blank and unrecoverable."""
    # First write: only stamps identity + status/confidence; structural
    # fields (statement / why / trigger_conditions) absent → end up blank.
    write_knowledge(
        project,
        "rules",
        {"knowledge_id": "rule-y", "spec_id": "REQ-001", "fields": {}},
        today=datetime.date(2026, 6, 1),
    )
    kn_v1 = _read_yaml(project / ".ai-memory/knowledge/rules/rule-y.yml")
    assert "statement" not in kn_v1  # blank baseline

    # Second write: carries real body → should fill the blanks.
    res = write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-y",
            "spec_id": "REQ-002",
            "fields": {
                "statement": "backfilled statement",
                "why": "backfilled why",
                "trigger_conditions": ["a", "b"],
            },
        },
        today=TODAY,
    )
    assert res["action"] == "merged"
    kn_v2 = _read_yaml(project / ".ai-memory/knowledge/rules/rule-y.yml")
    assert kn_v2["statement"] == "backfilled statement"
    assert kn_v2["why"] == "backfilled why"
    assert kn_v2["trigger_conditions"] == ["a", "b"]
    # related_requirements still appends (existing safety preserved)
    assert set(kn_v2["related_requirements"]) == {"REQ-001", "REQ-002"}

    # Third write: structural fields now populated → must NOT overwrite.
    write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-y",
            "spec_id": "REQ-003",
            "fields": {"statement": "different value", "why": "different why"},
        },
        today=TODAY,
    )
    kn_v3 = _read_yaml(project / ".ai-memory/knowledge/rules/rule-y.yml")
    assert kn_v3["statement"] == "backfilled statement"  # preserved
    assert kn_v3["why"] == "backfilled why"  # preserved


def test_rule_merge_never_overwrites_identity_fields(project: Path):
    """0.4.9: identity / lifecycle fields the writer manages (schema_version,
    knowledge_id, type, version, created_at, status, confidence) must never
    be copied from incoming payload during the blank-fill, even if the
    existing kn has e.g. status absent (which shouldn't happen but guard
    against payload abuse)."""
    write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-z",
            "fields": {"statement": "first"},
        },
        today=datetime.date(2026, 6, 1),
    )
    write_knowledge(
        project,
        "rules",
        {
            "knowledge_id": "rule-z",
            "fields": {
                "statement": "should not overwrite",
                "type": "ATTACKER_TYPE",
                "knowledge_id": "rule-attacker",
                "version": 99,
                "created_at": "1999-01-01",
            },
        },
        today=TODAY,
    )
    kn = _read_yaml(project / ".ai-memory/knowledge/rules/rule-z.yml")
    assert kn["knowledge_id"] == "rule-z"  # not attacker-controlled
    assert kn["type"] == "business_rule"  # writer-stamped, not attacker
    assert kn["version"] == 2  # writer-bumped
    assert kn["created_at"] == "2026-06-01"  # preserved
    assert kn["statement"] == "first"  # blank-fill didn't overwrite


def test_pitfall_merge_appends_seen_again_in(project: Path):
    write_knowledge(
        project,
        "pitfalls",
        {"signature": "npe", "spec_id": "REQ-001", "fields": {"symptom": "s"}},
        today=datetime.date(2026, 6, 1),
    )
    write_knowledge(
        project,
        "pitfalls",
        {"signature": "npe", "spec_id": "REQ-002", "fields": {"symptom": "s"}},
        today=TODAY,
    )
    kn = _read_yaml(project / ".ai-memory/knowledge/pitfalls/pit-npe.yml")
    assert "REQ-002" in (kn.get("seen_again_in") or [])


# ---------- validation / red lines ----------


def test_unknown_category_returns_errors_no_write(project: Path):
    res = write_knowledge(project, "bogus", {"fields": {}}, today=TODAY)
    assert res["errors"]
    assert not (project / ".ai-memory/knowledge").exists() or not any(
        (project / ".ai-memory/knowledge").rglob("*.yml")
    )


def test_missing_identity_returns_error(project: Path):
    # no knowledge_id / spec_id / signature / title → cannot derive id
    res = write_knowledge(project, "rules", {"fields": {"statement": "x"}}, today=TODAY)
    assert res["errors"]


def test_atomic_yaml_is_loadable(project: Path):
    write_knowledge(
        project,
        "modules",
        {
            "knowledge_id": "mod-sf-credit-main",
            "fields": {"scope": "table", "primary_entity": "tbl-sf_credit_main"},
        },
        today=TODAY,
    )
    kn = _read_yaml(project / ".ai-memory/knowledge/modules/mod-sf-credit-main.yml")
    assert isinstance(kn, dict)  # well-formed, fully written


def test_unmounted_volume_refused(tmp_path: Path):
    # project_root under an unmounted /Volumes/<name> → refuse, no crash
    fake = Path("/Volumes/NoSuchDrive-xyz/proj")
    res = write_knowledge(
        fake, "rules", {"knowledge_id": "rule-x", "fields": {"statement": "s"}}, today=TODAY
    )
    assert res["errors"]
    assert any("mount" in e.lower() or "volume" in e.lower() or "挂载" in e for e in res["errors"])
