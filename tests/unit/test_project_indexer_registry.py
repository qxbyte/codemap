"""Plan 1 Task 2: ProjectIndexer protocol + ProjectIndexerRegistry."""

from __future__ import annotations

from pathlib import Path

from codemap.core.models import IndexResult, Range, Symbol
from codemap.core.symbol import SymbolID
from codemap.indexers.project_base import ProjectIndexContext, ProjectIndexer
from codemap.indexers.project_registry import ProjectIndexerRegistry


class _Fake:
    name = "fake"
    version = "0.1.0"

    def index_project(self, ctx: ProjectIndexContext) -> IndexResult:
        sid = SymbolID.parse("scip-java . . . a/B#")
        return IndexResult(
            symbols=[
                Symbol(
                    id=sid,
                    kind="class",
                    language="java",
                    file="B.java",
                    range=Range(start_line=1, end_line=1),
                )
            ]
        )


def test_protocol_runtime_check() -> None:
    assert isinstance(_Fake(), ProjectIndexer)


def test_register_and_run() -> None:
    reg = ProjectIndexerRegistry()
    reg.register(_Fake())
    ix = reg.all()["fake"]
    res = ix.index_project(ProjectIndexContext(project_root=Path("."), config={}))
    assert len(res.symbols) == 1
