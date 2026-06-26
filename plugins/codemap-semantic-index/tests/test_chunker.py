"""Tests for the markdown chunker."""

from __future__ import annotations

from pathlib import Path

from codemap_semantic_index.chunker import (
    MAX_TOKENS,
    approx_token_count,
    chunk_knowledge_base,
    chunk_markdown,
)


def test_strips_frontmatter_and_extracts_h1() -> None:
    md = """---
knowledge_id: rule-x
type: business_rule
---

# Coupon rule title

## 一句话规则

Coupons can't stack with points.

## 为什么

Avoid double discounts.
"""
    chunks = chunk_markdown(
        md,
        knowledge_id="rule-x",
        category="rules",
        source_md="knowledge-base/rules/rule-x.md",
        source_yml=".ai-memory/knowledge/rules/rule-x.yml",
    )
    assert all(c.title == "Coupon rule title" for c in chunks)
    h2_titles = [c.h2_title for c in chunks]
    assert "一句话规则" in h2_titles
    assert "为什么" in h2_titles
    # Body is prefixed with knowledge_id / h2_title for context anchoring.
    for c in chunks:
        assert c.text.startswith(f"{c.knowledge_id} / {c.h2_title}")


def test_no_h2_falls_back_to_preamble_chunk() -> None:
    md = "# title\n\nbody without any sections."
    chunks = chunk_markdown(
        md,
        knowledge_id="rule-x",
        category="rules",
        source_md="x",
        source_yml="y",
    )
    assert len(chunks) == 1
    assert chunks[0].h2_title == ""
    assert "body without any sections" in chunks[0].text


def test_long_section_splits_into_windows() -> None:
    # Build a section that exceeds MAX_TOKENS
    body = "word " * (MAX_TOKENS * 2)  # ~ 2x over threshold
    md = f"# title\n\n## big section\n\n{body}"
    chunks = chunk_markdown(
        md,
        knowledge_id="case-big",
        category="cases",
        source_md="x",
        source_yml="y",
    )
    # Should split into multiple windows
    big_chunks = [c for c in chunks if c.h2_title == "big section"]
    assert len(big_chunks) > 1
    # All windows share the same chunk_id prefix
    assert all(c.chunk_id.startswith("case-big::big-section::w") for c in big_chunks)


def test_text_hash_is_stable_for_same_text() -> None:
    md = "# t\n\n## h2\n\nbody"
    a = chunk_markdown(md, knowledge_id="k", category="rules", source_md="x", source_yml="y")
    b = chunk_markdown(md, knowledge_id="k", category="rules", source_md="x", source_yml="y")
    assert [c.text_hash for c in a] == [c.text_hash for c in b]


def test_text_hash_changes_when_text_changes() -> None:
    a = chunk_markdown(
        "# t\n\n## h2\n\nbody one",
        knowledge_id="k",
        category="rules",
        source_md="x",
        source_yml="y",
    )
    b = chunk_markdown(
        "# t\n\n## h2\n\nbody two",
        knowledge_id="k",
        category="rules",
        source_md="x",
        source_yml="y",
    )
    assert a[0].text_hash != b[0].text_hash


def test_approx_token_count_cjk_vs_ascii() -> None:
    # 8 ASCII chars → 8/4 = 2 tokens
    assert approx_token_count("abcdefgh") == 2
    # 8 CJK chars → 8/2 = 4 tokens
    assert approx_token_count("一二三四五六七八") == 4


def test_chunk_knowledge_base_walks_5_categories(tmp_path: Path) -> None:
    for cat in ("rules", "business", "modules", "cases", "pitfalls"):
        cat_dir = tmp_path / "knowledge-base" / cat
        cat_dir.mkdir(parents=True)
        (cat_dir / f"x-{cat}.md").write_text(
            f"# title for {cat}\n\n## section\n\nbody {cat}.",
            encoding="utf-8",
        )
    chunks = chunk_knowledge_base(tmp_path)
    cats = {c.category for c in chunks}
    assert cats == {"rules", "business", "modules", "cases", "pitfalls"}


def test_chunk_knowledge_base_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert chunk_knowledge_base(tmp_path) == []


def test_source_paths_are_relative_to_project_root(tmp_path: Path) -> None:
    cat_dir = tmp_path / "knowledge-base" / "rules"
    cat_dir.mkdir(parents=True)
    (cat_dir / "rule-x.md").write_text("# t\n\n## s\n\nbody.", encoding="utf-8")
    chunks = chunk_knowledge_base(tmp_path)
    assert chunks[0].source_md == "knowledge-base/rules/rule-x.md"
    assert chunks[0].source_yml == ".ai-memory/knowledge/rules/rule-x.yml"


def test_chunk_to_dict_roundtrip() -> None:
    md = "# title\n\n## h2\n\nbody"
    c = chunk_markdown(md, knowledge_id="k", category="rules", source_md="x", source_yml="y")[0]
    d = c.to_dict()
    assert d["knowledge_id"] == "k"
    assert d["category"] == "rules"
    assert d["text"].startswith("k / h2")
    assert d["text_hash"]
