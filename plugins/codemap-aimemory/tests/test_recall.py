"""Tests for the token-based knowledge recall (P3-1)."""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.recall import recall, tokenize


def _seed_ai_memory(root: Path) -> None:
    (root / ".ai-memory" / "knowledge" / "rules").mkdir(parents=True)
    (root / ".ai-memory" / "knowledge" / "business").mkdir(parents=True)
    (root / ".ai-memory" / "knowledge" / "cases").mkdir(parents=True)
    (root / ".ai-memory" / "knowledge" / "pitfalls").mkdir(parents=True)
    (root / ".ai-memory" / "_global").mkdir(parents=True)


def _write_yml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


# ---------- tokenizer ----------


def test_tokenize_english_words_lowercased() -> None:
    assert tokenize("Coupon Mutex Rule") == {"coupon", "mutex", "rule"}


def test_tokenize_strips_short_english_words() -> None:
    assert "a" not in tokenize("a quick brown fox")
    assert "quick" in tokenize("a quick brown fox")


def test_tokenize_chinese_uses_char_bigrams() -> None:
    toks = tokenize("优惠券规则")
    # 4 chars → 3 bigrams
    assert "优惠" in toks
    assert "惠券" in toks
    assert "券规" in toks
    assert "规则" in toks


def test_tokenize_mixed_language() -> None:
    toks = tokenize("coupon 优惠券")
    assert "coupon" in toks
    assert "优惠" in toks


def test_tokenize_empty_returns_empty_set() -> None:
    assert tokenize("") == set()
    assert tokenize("    ") == set()


# ---------- recall: empty / no knowledge ----------


def test_recall_with_no_ai_memory_returns_empty(tmp_path: Path) -> None:
    result = recall("anything", tmp_path)
    assert result["knowledge"] == []
    assert result["matched_entities"] == []


def test_recall_with_empty_query_returns_empty_results(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-a.yml",
        {"knowledge_id": "rule-a", "title": "X"},
    )
    result = recall("", tmp_path)
    assert result["knowledge"] == []


# ---------- recall: basic ranking ----------


def test_recall_ranks_by_token_overlap(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {
            "knowledge_id": "rule-coupon-mutex",
            "title": "coupon and points cannot stack",
            "tags": ["coupon", "pricing"],
        },
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-unrelated.yml",
        {"knowledge_id": "rule-unrelated", "title": "audit log retention"},
    )
    result = recall("coupon stack", tmp_path)
    ids = [k["knowledge_id"] for k in result["knowledge"]]
    assert ids[0] == "rule-coupon-mutex"
    assert "rule-unrelated" not in ids


def test_recall_only_returns_top_k(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    for i in range(7):
        _write_yml(
            tmp_path / ".ai-memory" / "knowledge" / "rules" / f"rule-{i}.yml",
            {"knowledge_id": f"rule-{i}", "title": "coupon"},
        )
    result = recall("coupon", tmp_path, top_k=3)
    assert len(result["knowledge"]) == 3


def test_recall_title_hits_weighted_higher_than_body(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-title-hit.yml",
        {"knowledge_id": "rule-title-hit", "title": "coupon validation rule"},
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-body-hit.yml",
        {"knowledge_id": "rule-body-hit", "title": "X", "tags": ["coupon"]},
    )
    result = recall("coupon", tmp_path)
    assert result["knowledge"][0]["knowledge_id"] == "rule-title-hit"


# ---------- recall: filtering ----------


def test_recall_types_filter_restricts_categories(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-a.yml",
        {"knowledge_id": "rule-a", "title": "coupon"},
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "cases" / "case-a.yml",
        {"knowledge_id": "case-a", "title": "coupon"},
    )
    result = recall("coupon", tmp_path, types=["rules"])
    cats = {k["category"] for k in result["knowledge"]}
    assert cats == {"rules"}


# ---------- recall: chinese ----------


def test_recall_chinese_query_hits_chinese_title(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {"knowledge_id": "rule-coupon-mutex", "title": "优惠券和积分不能同时使用"},
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-other.yml",
        {"knowledge_id": "rule-other", "title": "完全无关的规则"},
    )
    result = recall("优惠券规则", tmp_path)
    ids = [k["knowledge_id"] for k in result["knowledge"]]
    assert ids[0] == "rule-coupon-mutex"


# ---------- recall: searchable fields coverage ----------


def test_recall_matches_related_code_entity(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-a.yml",
        {
            "knowledge_id": "rule-a",
            "title": "X",
            "related_code": [{"entity": "fn-validate-coupon"}],
        },
    )
    result = recall("validate", tmp_path)
    assert result["knowledge"][0]["knowledge_id"] == "rule-a"


def test_recall_matches_pitfall_symptom_and_fix(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "pitfalls" / "pit-npe.yml",
        {
            "knowledge_id": "pit-amount-npe",
            "title": "amount null NPE",
            "symptom": "BigDecimal.add throws NullPointerException",
            "fix": ["wrap with Optional.ofNullable"],
        },
    )
    result = recall("nullpointerexception", tmp_path)
    assert result["knowledge"][0]["knowledge_id"] == "pit-amount-npe"


# ---------- recall: matched_entities from _global ----------


def test_recall_matched_entities_from_global_index(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "_global" / "entities.yml",
        {
            "entities": [
                {"id": "fn-calc-coupon", "type": "function", "source": "code"},
                {"id": "fn-other", "type": "function", "source": "code"},
                {"id": "tbl-orders", "type": "table", "source": "both"},
            ]
        },
    )
    result = recall("coupon", tmp_path)
    assert result["matched_entities"] == ["fn-calc-coupon"]


def test_recall_matched_entities_empty_when_no_global(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    result = recall("anything", tmp_path)
    assert result["matched_entities"] == []


# ---------- recall: malformed yml tolerated ----------


def test_recall_skips_malformed_yml(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    (tmp_path / ".ai-memory" / "knowledge" / "rules" / "broken.yml").write_text(
        "not: valid: ::: yaml"
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-good.yml",
        {"knowledge_id": "rule-good", "title": "coupon"},
    )
    result = recall("coupon", tmp_path)
    assert result["knowledge"][0]["knowledge_id"] == "rule-good"


# ---------- recall: output shape ----------


def test_recall_result_carries_required_fields(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {
            "knowledge_id": "rule-coupon",
            "type": "business_rule",
            "title": "Coupon rule",
            "statement": "Coupons can't stack with points",
        },
    )
    result = recall("coupon", tmp_path)
    item = result["knowledge"][0]
    assert item["knowledge_id"] == "rule-coupon"
    assert item["type"] == "business_rule"
    assert item["category"] == "rules"
    assert item["title"] == "Coupon rule"
    assert "Coupons can't stack" in item["summary"]
    assert item["score"] >= 1
    assert item["file"].endswith("rule-coupon.yml")
    assert "query" in result
    assert "tokens" in result
    # P4-1/P4-2 fields always present
    assert "freshness_score" in item
    assert "ranked_score" in item
    assert "stale" in item


# ---------- with_content (P3-2 enablement) ----------


def test_recall_with_content_adds_rule_fields(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {
            "knowledge_id": "rule-coupon-mutex",
            "type": "business_rule",
            "title": "优惠券和积分互斥",
            "statement": "Coupons and points can't both apply to the same order.",
            "why": "Prevents stacking discounts beyond margin.",
            "exceptions": ["VIP ≥ 8"],
            "enforcement": ["service layer throws", "frontend disables checkbox"],
        },
    )
    result = recall("coupon", tmp_path, with_content=True)
    item = result["knowledge"][0]
    assert "content" in item
    c = item["content"]
    assert "Coupons and points" in c["statement"]
    assert "stacking discounts" in c["why"]
    assert c["exceptions"] == ["VIP ≥ 8"]
    assert len(c["enforcement"]) == 2


def test_recall_with_content_omits_empty_fields(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-x.yml",
        {
            "knowledge_id": "rule-x",
            "title": "Minimal rule",
            "statement": "X",  # only statement; no why/exceptions/enforcement
        },
    )
    result = recall("rule", tmp_path, with_content=True)
    item = result["knowledge"][0]
    assert item["content"] == {"statement": "X"}


def test_recall_with_content_pitfall_fields(tmp_path: Path) -> None:
    (tmp_path / ".ai-memory" / "knowledge" / "pitfalls").mkdir(parents=True)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "pitfalls" / "pit-x.yml",
        {
            "knowledge_id": "pit-amount-null",
            "type": "pitfall",
            "title": "amount null NPE",
            "symptom": "NullPointerException on BigDecimal.add",
            "root_cause": "no requireNonNullElse guard",
            "fix": ["Optional.ofNullable(amount).orElse(ZERO)"],
            "affects": ["src/order/query.js"],
        },
    )
    result = recall("amount", tmp_path, with_content=True)
    item = result["knowledge"][0]
    c = item["content"]
    assert "NullPointerException" in c["symptom"]
    assert "requireNonNullElse" in c["root_cause"]
    assert "Optional.ofNullable" in c["fix"][0]
    assert "src/order/query.js" in c["affects"]


def test_recall_without_with_content_no_content_field(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-x.yml",
        {"knowledge_id": "rule-x", "title": "X", "statement": "stmt"},
    )
    result = recall("rule", tmp_path, with_content=False)
    assert "content" not in result["knowledge"][0]


# ---------- freshness ranking ----------


def test_recall_ranks_fresher_above_stale_with_same_score(tmp_path: Path) -> None:
    """Two hits with identical token score: the one updated today should
    outrank the one updated 2 years ago."""
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-fresh.yml",
        {"knowledge_id": "rule-fresh", "title": "coupon", "updated_at": "2026-06-26"},
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-stale.yml",
        {"knowledge_id": "rule-stale", "title": "coupon", "updated_at": "2024-06-26"},
    )
    result = recall("coupon", tmp_path)
    ids = [k["knowledge_id"] for k in result["knowledge"]]
    assert ids == ["rule-fresh", "rule-stale"]
    # fresh < threshold check
    fresh = next(k for k in result["knowledge"] if k["knowledge_id"] == "rule-fresh")
    stale = next(k for k in result["knowledge"] if k["knowledge_id"] == "rule-stale")
    assert fresh["freshness_score"] > stale["freshness_score"]
    assert fresh["stale"] is False
    assert stale["stale"] is True  # 2 years old → way below 0.5 threshold


def test_recall_freshness_uses_code_change_map(tmp_path: Path) -> None:
    """Code churn pulls freshness down even for a recently-updated yml."""
    _seed_ai_memory(tmp_path)
    (tmp_path / ".ai-memory" / "entities").mkdir(parents=True)
    _write_yml(
        tmp_path / ".ai-memory" / "entities" / "functions.yml",
        [{"id": "fn-x", "file": "src/x.py", "change_count_90d": 30}],
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-churned.yml",
        {
            "knowledge_id": "rule-churned",
            "title": "rule about src/x",
            "updated_at": "2026-06-26",
            "related_code": [{"file": "src/x.py"}],
        },
    )
    result = recall("rule", tmp_path)
    item = result["knowledge"][0]
    # 30 changes → code_factor = 1 / (1 + 0.05 * 30) = 0.4 → freshness ≈ 0.4
    assert item["freshness_score"] < 0.5
    assert item["stale"] is True
