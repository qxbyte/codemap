"""Tests for the optional LLM enrichment overlay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from codemap_aimemory.enrich import enrich, load_enrichment

from codemap.core.models import Range, Symbol
from codemap.core.symbol import SymbolID
from codemap.io.json_store import JsonStore

_FN = "scip-java . . . src/Svc.java/Svc#calc()."
_CLS = "scip-java . . . src/Svc.java/Svc#"


class _FakeLlm:
    model = "claude-test"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def describe(self, symbol: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(symbol)
        return {
            "business_meaning": f"meaning-of-{symbol.get('symbol_id', '?')[-10:]}",
            "related_rules": ["rule-x"],
        }


def _seed(store: JsonStore) -> None:
    store.upsert_symbols(
        [
            Symbol(
                id=SymbolID.parse(_FN),
                kind="method",
                language="java",
                file="src/Svc.java",
                range=Range(start_line=1, end_line=5),
                signature="int calc()",
            ),
            Symbol(
                id=SymbolID.parse(_CLS),
                kind="class",
                language="java",
                file="src/Svc.java",
                range=Range(start_line=1, end_line=5),
            ),
        ]
    )


# ----- load_enrichment -----


def test_load_enrichment_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    assert load_enrichment(tmp_path / "no-such") == {}


def test_load_enrichment_reads_yaml_indexed_by_symbol_id(tmp_path: Path) -> None:
    d = tmp_path / "enrichment"
    d.mkdir()
    (d / "a.yml").write_text(
        yaml.safe_dump({"symbol_id": "sid-1", "business_meaning": "x"})
    )
    (d / "b.yml").write_text(
        yaml.safe_dump({"symbol_id": "sid-2", "business_meaning": "y"})
    )
    loaded = load_enrichment(d)
    assert loaded["sid-1"]["business_meaning"] == "x"
    assert loaded["sid-2"]["business_meaning"] == "y"


def test_load_enrichment_skips_yaml_without_symbol_id(tmp_path: Path) -> None:
    d = tmp_path / "enrichment"
    d.mkdir()
    (d / "junk.yml").write_text("foo: bar\n")
    assert load_enrichment(d) == {}


# ----- enrich -----


def test_enrich_writes_one_file_per_fn_method(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.commit()
        written = enrich(
            store, _FakeLlm(), tmp_path / ".ai-memory", generated_at="2026-06-24"
        )
    assert len(written) == 1
    loaded = load_enrichment(tmp_path / ".ai-memory" / "enrichment")
    assert _FN in loaded
    assert _CLS not in loaded  # only method/function
    payload = loaded[_FN]
    assert payload["confidence"] == "llm"
    assert payload["source_model"] == "claude-test"
    assert payload["generated_at"] == "2026-06-24"


def test_enrich_changed_only_skips_existing(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.commit()
        out = tmp_path / ".ai-memory"
        # 1st pass: writes everything
        first = enrich(store, _FakeLlm(), out, generated_at="d1")
        # 2nd pass with changed_only=True: should write nothing new
        second = enrich(
            store, _FakeLlm(), out, generated_at="d2", changed_only=True
        )
    assert first
    assert second == []


def test_enrich_passes_signature_and_file_to_llm(tmp_path: Path) -> None:
    llm = _FakeLlm()
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.commit()
        enrich(store, llm, tmp_path / ".ai-memory", generated_at="d")
    assert llm.calls[0]["signature"] == "int calc()"
    assert llm.calls[0]["file"] == "src/Svc.java"


def test_enrich_skipped_classes_dont_invoke_llm(tmp_path: Path) -> None:
    llm = _FakeLlm()
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)  # also has a class symbol
        store.commit()
        enrich(store, llm, tmp_path / ".ai-memory", generated_at="d")
    # only the method, not the class, hits the LLM
    assert len(llm.calls) == 1
