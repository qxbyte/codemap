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
