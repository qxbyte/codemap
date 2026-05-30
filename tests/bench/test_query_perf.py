"""Query-latency benchmarks: callers, callees, walk, shortest_path.

Run with::

    pytest tests/bench --benchmark-only -m bench

Each test opens the indexed CodeMap repo read-only and exercises one
hot-path query against a known internal symbol.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.core.graph import shortest_path, walk_chain
from codemap.core.symbol import SymbolID
from codemap.io.json_store import JsonStore

pytestmark = pytest.mark.bench

# A symbol that exists in the CodeMap source: the public entry point of
# the Python indexer. It has both callers (the orchestration in
# ``cli/commands/index.py``) and callees (`ast.parse`, `_Visitor.visit`).
_PY_INDEXER_ID = "scip-python . . . src/codemap/indexers/python.py/PythonIndexer#index_file()."


@pytest.fixture
def opened_store(codemap_repo_indexed: Path):  # type: ignore[no-untyped-def]
    with JsonStore.open(codemap_repo_indexed / ".codemap", mode="r") as store:
        yield store


def test_bench_callers(benchmark, opened_store) -> None:  # type: ignore[no-untyped-def]
    """Target (design §21): callers P95 ≤ 50 ms."""
    sid = SymbolID.parse(_PY_INDEXER_ID)
    benchmark(opened_store.callers, sid)


def test_bench_callees(benchmark, opened_store) -> None:  # type: ignore[no-untyped-def]
    """Target (design §21): callees P95 ≤ 50 ms."""
    sid = SymbolID.parse(_PY_INDEXER_ID)
    benchmark(opened_store.callees, sid)


def test_bench_walk_chain_depth_10(benchmark, opened_store) -> None:  # type: ignore[no-untyped-def]
    """Target (design §21): trace P95 ≤ 200 ms (depth 10)."""
    sid = SymbolID.parse(_PY_INDEXER_ID)
    benchmark(walk_chain, sid, opened_store, max_depth=10)


def test_bench_search_keyword(benchmark, opened_store) -> None:  # type: ignore[no-untyped-def]
    """Search latency on a populated index."""
    benchmark(opened_store.search, "PythonIndexer", limit=10)


def test_bench_shortest_path_unreachable(benchmark, opened_store) -> None:  # type: ignore[no-untyped-def]
    """Worst-case bidirectional BFS: no path exists, max depth exhausted."""
    a = SymbolID.parse("scip-python . . . src/codemap/core/symbol.py/SymbolID#")
    b = SymbolID.parse("scip-python . . . src/codemap/cli/commands/doctor.py/register().")
    benchmark(shortest_path, a, b, opened_store, max_depth=4)
