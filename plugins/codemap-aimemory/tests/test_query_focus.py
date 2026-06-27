"""FIX-3a: query understanding — extract_query_focus trims a whole spec doc
to its salient signal (headings + entity-like tokens), instead of dumping the
entire document as the recall query (which token-explodes and washes out
ranking)."""

from __future__ import annotations

from codemap_aimemory.recall import extract_query_focus

SPEC = """---
spec_id: REQ-001
project_root: /abs/secretdir/proj
---

# 订单批量改地址

## 背景

需要给 SfCreditMain 增加批量接口, 走 /api/order/batch-address, 写 sf_order 表.

## 范围

- 涉及 com.helloshop.order.OrderController
"""


def test_strips_frontmatter_noise():
    focus = extract_query_focus(SPEC)
    assert "secretdir" not in focus  # frontmatter project_root must not leak in
    assert "project_root" not in focus


def test_retains_headings():
    focus = extract_query_focus(SPEC)
    assert "优惠券" not in focus  # sanity: unrelated term absent
    assert "批量改地址" in focus  # H1 heading retained


def test_extracts_entity_like_tokens():
    focus = extract_query_focus(SPEC)
    assert "SfCreditMain" in focus
    assert "sf_order" in focus
    assert "/api/order/batch-address" in focus
    assert "com.helloshop.order.OrderController" in focus


def test_small_doc_falls_back_to_body():
    out = extract_query_focus("# anything")
    assert "anything" in out


def test_empty_text():
    assert extract_query_focus("") == ""


def test_caps_length():
    big = "# h\n\n" + ("word " * 5000)
    out = extract_query_focus(big, max_chars=500)
    assert len(out) <= 500
