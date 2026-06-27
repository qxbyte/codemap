"""FIX-3b: cold-start L1 fallback — recall surfaces enriched code entities
(`code_context`) from .ai-memory/entities + _global, so the *first* spec on a
project (empty knowledge/) still gets a relevant code map instead of nothing.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.recall import recall


def _seed(root: Path) -> None:
    ent = root / ".ai-memory" / "entities"
    ent.mkdir(parents=True)
    (ent / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "fn-calc-price",
                    "type": "function",
                    "file": "src/order/pricing.py",
                    "signature": "def calc_price(order, user)",
                    "called_by": ["fn-order-create"],
                    "calls": ["fn-apply-coupon"],
                    "related_tables": ["tbl-sf_order"],
                    "change_count_90d": 5,
                }
            ],
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    glob = root / ".ai-memory" / "_global"
    glob.mkdir(parents=True)
    (glob / "entities.yml").write_text(
        yaml.safe_dump(
            {
                "entities": [
                    {
                        "id": "fn-calc-price",
                        "type": "function",
                        "source": "both",
                        "knowledge_refs": ["rule-coupon-mutex"],
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_code_context_enriches_matched_entity_when_knowledge_empty(tmp_path: Path):
    _seed(tmp_path)
    result = recall("calc price", tmp_path, top_k=5)
    assert result["knowledge"] == []  # no knowledge yet (cold start)
    cc = result["code_context"]
    assert cc, "expected code_context to bridge the empty-knowledge cold start"
    entry = next(e for e in cc if e["id"] == "fn-calc-price")
    assert entry["signature"] == "def calc_price(order, user)"
    assert entry["called_by"] == ["fn-order-create"]
    assert entry["related_tables"] == ["tbl-sf_order"]
    assert entry["knowledge_refs"] == ["rule-coupon-mutex"]


def test_code_context_empty_when_no_entity_match(tmp_path: Path):
    _seed(tmp_path)
    result = recall("nonexistent zzz", tmp_path, top_k=5)
    assert result["code_context"] == []


def test_code_context_absent_gracefully_without_entities(tmp_path: Path):
    (tmp_path / ".ai-memory").mkdir()
    result = recall("anything", tmp_path, top_k=5)
    assert result["code_context"] == []
