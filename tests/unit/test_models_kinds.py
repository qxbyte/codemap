"""Plan 1 Task 1: new SymbolKind "table" + new EdgeKinds "overrides"/"accesses_table"."""

from __future__ import annotations

from codemap.core.models import Edge, Range, Symbol
from codemap.core.symbol import SymbolID

SID = SymbolID.parse("scip-java . . . a/B#")
SID2 = SymbolID.parse("scip-java . . . a/tbl.")


def test_table_symbol_kind_allowed() -> None:
    s = Symbol(
        id=SID2,
        kind="table",
        language="sql",
        file="m.xml",
        range=Range(start_line=1, end_line=1),
    )
    assert s.kind == "table"


def test_new_edge_kinds_allowed() -> None:
    for k in ("overrides", "accesses_table"):
        e = Edge(source=SID, target=SID2, kind=k)
        assert e.kind == k
