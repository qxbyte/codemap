"""Tests for ``AiMemoryEmitter``."""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.emitter import AiMemoryEmitter

from codemap.core.models import Edge, Range, Symbol
from codemap.core.symbol import SymbolID
from codemap.emitters.base import EmitContext
from codemap.io.json_store import JsonStore

_FN = "scip-java . . . src/Svc.java/Svc#calc()."
_FN2 = "scip-java . . . src/Ctl.java/Ctl#go()."
_TBL = "scip-table . . . sf_coupon#"


def _seed(store: JsonStore) -> None:
    store.upsert_symbols(
        [
            Symbol(
                id=SymbolID.parse(_FN),
                kind="method",
                language="java",
                file="src/Svc.java",
                range=Range(start_line=10, end_line=20),
                signature="int calc()",
                extra={"change_count_90d": 5},
            ),
            Symbol(
                id=SymbolID.parse(_FN2),
                kind="method",
                language="java",
                file="src/Ctl.java",
                range=Range(start_line=3, end_line=8),
                signature="void go()",
            ),
            Symbol(
                id=SymbolID.parse(_TBL),
                kind="table",
                language="sql",
                file="m.xml",
                range=Range(start_line=1, end_line=1),
            ),
        ]
    )
    store.upsert_edges(
        [
            Edge(
                source=SymbolID.parse(_FN2),
                target=SymbolID.parse(_FN),
                kind="calls",
                confidence="medium",
            ),
            Edge(
                source=SymbolID.parse(_FN),
                target=SymbolID.parse(_TBL),
                kind="accesses_table",
                confidence="high",
            ),
        ]
    )


def _emit(tmp_path: Path) -> Path:
    out = tmp_path / ".ai-memory"
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.commit()
        AiMemoryEmitter().emit(store, EmitContext(project_root=tmp_path, output_dir=out))
    return out


# ----- basic structure -----


def test_emits_all_expected_files(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    expected = [
        "entities/functions.yml",
        "entities/tables.yml",
        "entities/files.yml",
        "relations/call-graph.yml",
        "relations/table-relations.yml",
        "relations/rule-constraints.yml",
    ]
    for rel in expected:
        assert (out / rel).is_file(), f"missing {rel}"


def test_functions_yml_carries_metadata(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    fns = yaml.safe_load((out / "entities/functions.yml").read_text())
    by_sid = {fn["symbol_id"]: fn for fn in fns}
    fn_calc = by_sid[_FN]
    assert fn_calc["type"] == "function"
    assert fn_calc["change_count_90d"] == 5
    assert fn_calc["business_meaning"] is None  # no enrichment present
    assert fn_calc["line_range"] == [10, 20]
    assert fn_calc["signature"] == "int calc()"
    assert "fn-go" in fn_calc["called_by"]  # Ctl.go → Svc.calc
    assert "tbl-sf_coupon" in fn_calc["related_tables"]


def test_tables_yml_has_table_entity(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    tables = yaml.safe_load((out / "entities/tables.yml").read_text())
    assert any(t["symbol_id"] == _TBL and t["type"] == "table" for t in tables)


def test_files_yml_lists_unique_paths(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    files = yaml.safe_load((out / "entities/files.yml").read_text())
    paths = {f["path"] for f in files}
    assert {"src/Svc.java", "src/Ctl.java", "m.xml"} <= paths


# ----- relations -----


def test_call_graph_yml(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    rels = yaml.safe_load((out / "relations/call-graph.yml").read_text())
    assert any(r["from"] == "fn-go" and r["to"] == "fn-calc" and r["type"] == "calls" for r in rels)


def test_table_relations_yml(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    rels = yaml.safe_load((out / "relations/table-relations.yml").read_text())
    assert rels[0] == {
        "from": "fn-calc",
        "to": "tbl-sf_coupon",
        "type": "accesses_table",
        "confidence": "high",
    }


def test_rule_constraints_yml_is_empty_placeholder(tmp_path: Path) -> None:
    out = _emit(tmp_path)
    assert (
        yaml.safe_load((out / "relations/rule-constraints.yml").read_text()) is None
        or yaml.safe_load((out / "relations/rule-constraints.yml").read_text()) == []
    )


# ----- enrichment overlay -----


def test_enrichment_overlay_fills_business_meaning(tmp_path: Path) -> None:
    out = tmp_path / ".ai-memory"
    (out / "enrichment").mkdir(parents=True)
    (out / "enrichment" / "x.yml").write_text(
        yaml.safe_dump(
            {
                "symbol_id": _FN,
                "business_meaning": "计算订单价格",
                "related_rules": ["rule-coupon-mutex"],
                "confidence": "llm",
                "source_model": "claude-test",
            },
            allow_unicode=True,
        )
    )
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.commit()
        AiMemoryEmitter().emit(store, EmitContext(project_root=tmp_path, output_dir=out))
    fns = yaml.safe_load((out / "entities/functions.yml").read_text())
    fn_calc = next(fn for fn in fns if fn["symbol_id"] == _FN)
    assert fn_calc["business_meaning"] == "计算订单价格"
    assert fn_calc["related_rules"] == ["rule-coupon-mutex"]


# ----- edge filtering -----


def test_edges_to_unknown_symbols_are_dropped(tmp_path: Path) -> None:
    unknown = "scip-java . . . src/U.java/U#u()."
    with JsonStore.open(tmp_path / ".codemap") as store:
        _seed(store)
        store.upsert_edges(
            [
                Edge(
                    source=SymbolID.parse(_FN),
                    target=SymbolID.parse(unknown),
                    kind="calls",
                    confidence="medium",
                )
            ]
        )
        store.commit()
        out = tmp_path / ".ai-memory"
        AiMemoryEmitter().emit(store, EmitContext(project_root=tmp_path, output_dir=out))
    rels = yaml.safe_load((out / "relations/call-graph.yml").read_text())
    assert not any(r["to"].endswith("-u") for r in rels)
