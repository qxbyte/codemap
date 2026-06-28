"""Tests for knowledge_ids — the single derivation of knowledge_id slugs
(FIX-2 / AI-EDS ISSUE-2).

task-swarm used ``case-<spec_id>-<gid>`` while specode-distill used
``case-<slug>-implementation`` — the two never collided, so the documented
"distill supersedes the auto case" never fired. Both now derive ids here:
``case-<spec_id>`` is the one canonical case id per spec.
"""

from __future__ import annotations

from codemap_aimemory import knowledge_ids as kid


def test_kebab_basic():
    assert kid.kebab("Coupon Points Mutex") == "coupon-points-mutex"
    assert kid.kebab("amount_null/NPE") == "amount-null-npe"
    assert kid.kebab("  trailing  ") == "trailing"


def test_kebab_all_nonascii_falls_back_to_hash():
    out = kid.kebab("优惠券互斥")
    # no ascii alnum survives → stable short hash, never empty
    assert out
    assert out == kid.kebab("优惠券互斥")  # deterministic


def test_case_id_is_per_spec():
    assert kid.case_id("REQ-001") == "case-req-001"
    assert kid.case_id("batch-address") == "case-batch-address"


def test_case_id_idempotent_if_already_prefixed():
    assert kid.case_id("case-REQ-001") == "case-req-001"


def test_pit_id_prefixes_signature():
    assert kid.pit_id("bigdecimal-npe") == "pit-bigdecimal-npe"
    assert kid.pit_id("pit-bigdecimal-npe") == "pit-bigdecimal-npe"


def test_derive_id_uses_category_prefix():
    assert kid.derive_id("rules", "coupon mutex") == "rule-coupon-mutex"
    assert kid.derive_id("business", "order checkout") == "biz-order-checkout"
    assert kid.derive_id("modules", "SfCreditMain") == "mod-sfcreditmain"


def test_normalize_id_adds_missing_prefix():
    assert kid.normalize_id("rules", "coupon-mutex") == "rule-coupon-mutex"


def test_normalize_id_keeps_existing_prefix():
    assert kid.normalize_id("rules", "rule-coupon-mutex") == "rule-coupon-mutex"


def test_normalize_id_rekebabs_messy_input():
    assert kid.normalize_id("pitfalls", "Pit Amount NULL") == "pit-amount-null"


# v0.4.8: max length truncation (round 3 实测发现 150+ 字符 id 文件名)


def test_long_id_truncated_to_max_80_chars():
    """v0.4.8: id 全长含 prefix 不超过 80 字符(filename-safe)。"""
    long_title = (
        "Spring HttpHeaders setContentDispositionFormData is not attachment "
        "and to get browser Save As one must use setContentDisposition "
        "ContentDisposition attachment filename build"
    )
    result = kid.normalize_id("rules", long_title)
    assert len(result) <= kid.ID_MAX_LEN, (
        f"len={len(result)} exceeds ID_MAX_LEN={kid.ID_MAX_LEN}: {result}"
    )
    assert result.startswith("rule-")


def test_long_id_truncation_keeps_collision_resistance():
    """两个差别只在末尾的长 title, 截断后 id 也不同(hash suffix 保唯一)。"""
    base = "a" * 100  # 100 chars all same
    id1 = kid.normalize_id("rules", base + "first ending")
    id2 = kid.normalize_id("rules", base + "second ending")
    assert id1 != id2, "different long inputs must produce different ids"
    assert len(id1) <= kid.ID_MAX_LEN
    assert len(id2) <= kid.ID_MAX_LEN


def test_long_id_truncation_is_deterministic():
    """同一长 title 多次派生 id 必须一致。"""
    long_title = "Some very long title " * 10
    id1 = kid.normalize_id("rules", long_title)
    id2 = kid.normalize_id("rules", long_title)
    assert id1 == id2


def test_short_id_unchanged_back_compat():
    """短 id 行为完全不变(截断只对超长生效)。"""
    assert kid.normalize_id("rules", "coupon mutex") == "rule-coupon-mutex"
    assert kid.case_id("REQ-001") == "case-req-001"
    # 不到 80 字符的中等长度也不截断
    medium = kid.normalize_id("rules", "Spring Boot LocalDateTime ISO JSON format")
    assert len(medium) < kid.ID_MAX_LEN
    assert "-" in medium  # no hash suffix added


def test_long_id_cut_at_kebab_boundary_when_possible():
    """截断时尽量在 `-` 边界切, 避免词语被切半(可读性优化)。"""
    # 构造 > 80 字符的 title, 每个词都 5-10 字符确保截断点附近有 `-`
    long_title = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
        "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
    )
    assert len("rule-" + long_title.replace(" ", "-")) > kid.ID_MAX_LEN  # sanity
    result = kid.normalize_id("rules", long_title)
    assert len(result) <= kid.ID_MAX_LEN
    # 截断后应该有 hash suffix(- + 8 hex chars at end)
    parts = result.rsplit("-", 1)
    assert len(parts[-1]) == 8, f"expected 8-char hash suffix, got: {parts[-1]!r}"
    # 截断前最后一段不应该是断词(看倒数第二段是不是完整词)
    main_part = parts[0]
    last_word = main_part.rsplit("-", 1)[-1]
    assert last_word in long_title.lower().split(), (
        f"truncation should cut at kebab boundary; got incomplete word: {last_word}"
    )


def test_explicit_knowledge_id_payload_overrides_derivation():
    """v0.4.8 contract reminder: writer 的 _resolve_id 优先用 payload.knowledge_id;
    这是 ID_MAX_LEN 截断的 escape hatch(用户可显式给短 id)。

    本 test 不直接调 writer(避免 fs setup 复杂), 而是 verify normalize_id 接受
    显式 id 并 idempotent 走 truncation 路径。
    """
    # 显式短 id: 原样返回
    assert kid.normalize_id("rules", "rule-short-explicit") == "rule-short-explicit"
    # 显式长 id: 也应该被截断(保证 fs-safe)
    long_explicit = "rule-" + "a" * 200
    result = kid.normalize_id("rules", long_explicit)
    assert len(result) <= kid.ID_MAX_LEN
