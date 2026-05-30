"""Unit tests for ``codemap.core.graph`` — walk_chain and shortest_path."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

import pytest

from codemap.core.graph import shortest_path, walk_chain
from codemap.core.models import Edge, Range, Symbol
from codemap.core.symbol import SymbolID


def _sid(letter: str) -> SymbolID:
    return SymbolID.parse(f"scip-test . . . {letter}.")


def _sym(letter: str) -> Symbol:
    return Symbol(
        id=_sid(letter),
        kind="function",
        language="test",
        file=PurePosixPath(f"{letter}.py"),
        range=Range(start_line=1, end_line=1),
    )


class _StubStore:
    """Minimal ReadOnlyStore that answers callees / callers from a fixed edge list."""

    def __init__(self, edges: list[Edge], symbols: list[Symbol] | None = None) -> None:
        self._edges = edges
        self._symbols = {str(s.id): s for s in (symbols or [])}
        self._callers_idx: dict[str, list[Edge]] = defaultdict(list)
        self._callees_idx: dict[str, list[Edge]] = defaultdict(list)
        for e in edges:
            self._callers_idx[str(e.target)].append(e)
            self._callees_idx[str(e.source)].append(e)

    def callees(self, sid, *, depth=1):
        return list(self._callees_idx[str(sid)])

    def callers(self, sid, *, depth=1):
        return list(self._callers_idx[str(sid)])

    def get(self, sid):
        return self._symbols.get(str(sid))

    # Methods the Protocol demands but tests don't need.
    def iter_symbols(self):  # pragma: no cover
        return iter(self._symbols.values())

    def iter_edges(self):  # pragma: no cover
        return iter(self._edges)

    def search(self, query, *, limit=10):  # pragma: no cover
        return []

    def manifest(self):  # pragma: no cover
        raise NotImplementedError


def _edge(s: str, t: str, kind: str = "calls") -> Edge:
    return Edge(source=_sid(s), target=_sid(t), kind=kind)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# walk_chain
# ---------------------------------------------------------------------------


def test_walk_chain_linear() -> None:
    store = _StubStore([_edge("a", "b"), _edge("b", "c")])
    root = walk_chain(_sid("a"), store, max_depth=5)
    assert root.depth == 0
    assert len(root.children) == 1
    assert root.children[0].depth == 1
    assert len(root.children[0].children) == 1
    assert root.children[0].children[0].depth == 2
    assert root.children[0].children[0].children == []


def test_walk_chain_branches() -> None:
    store = _StubStore([_edge("a", "b"), _edge("a", "c"), _edge("a", "d")])
    root = walk_chain(_sid("a"), store, max_depth=1)
    child_ids = sorted(str(c.symbol_id) for c in root.children)
    assert len(child_ids) == 3


def test_walk_chain_depth_zero_returns_root_only() -> None:
    store = _StubStore([_edge("a", "b")])
    root = walk_chain(_sid("a"), store, max_depth=0)
    assert root.children == []


def test_walk_chain_depth_limit() -> None:
    store = _StubStore([_edge("a", "b"), _edge("b", "c"), _edge("c", "d")])
    root = walk_chain(_sid("a"), store, max_depth=2)
    # Depth 2 means we see a → b → c, but not d.
    assert root.children[0].children[0].symbol_id == _sid("c")
    assert root.children[0].children[0].children == []


def test_walk_chain_breaks_cycles() -> None:
    store = _StubStore([_edge("a", "b"), _edge("b", "a")])
    root = walk_chain(_sid("a"), store, max_depth=5)
    # b is visited first (depth 1), a is already visited (the root) so no
    # repeat — chain terminates.
    assert root.children[0].symbol_id == _sid("b")
    assert root.children[0].children == []


def test_walk_chain_rejects_negative_depth() -> None:
    store = _StubStore([])
    with pytest.raises(ValueError, match="max_depth"):
        walk_chain(_sid("a"), store, max_depth=-1)


def test_walk_chain_isolated_node() -> None:
    store = _StubStore([])
    root = walk_chain(_sid("a"), store, max_depth=5)
    assert root.children == []


# ---------------------------------------------------------------------------
# shortest_path
# ---------------------------------------------------------------------------


def test_shortest_path_direct_neighbour() -> None:
    store = _StubStore([_edge("a", "b")])
    path = shortest_path(_sid("a"), _sid("b"), store, max_depth=3)
    assert path is not None
    assert len(path) == 1
    assert path[0].source == _sid("a")
    assert path[0].target == _sid("b")


def test_shortest_path_multi_hop() -> None:
    store = _StubStore([_edge("a", "b"), _edge("b", "c"), _edge("c", "d")])
    path = shortest_path(_sid("a"), _sid("d"), store, max_depth=5)
    assert path is not None
    assert [str(e.source) for e in path] == [str(_sid(x)) for x in "abc"]


def test_shortest_path_prefers_shorter() -> None:
    # Two routes from a to d: a→b→d (2 hops) and a→c→x→d (3 hops)
    store = _StubStore(
        [_edge("a", "b"), _edge("b", "d"), _edge("a", "c"), _edge("c", "x"), _edge("x", "d")]
    )
    path = shortest_path(_sid("a"), _sid("d"), store, max_depth=5)
    assert path is not None
    assert len(path) == 2


def test_shortest_path_returns_none_when_unreachable() -> None:
    store = _StubStore([_edge("a", "b"), _edge("c", "d")])
    path = shortest_path(_sid("a"), _sid("d"), store, max_depth=5)
    assert path is None


def test_shortest_path_same_node_returns_empty() -> None:
    store = _StubStore([_edge("a", "b")])
    path = shortest_path(_sid("a"), _sid("a"), store, max_depth=5)
    assert path == []


def test_shortest_path_depth_cuts_off() -> None:
    # a → b → c → d → e; max_depth=2 from each side covers 4 hops total,
    # which is enough. max_depth=1 would not be (2 hops max).
    store = _StubStore([_edge("a", "b"), _edge("b", "c"), _edge("c", "d"), _edge("d", "e")])
    assert shortest_path(_sid("a"), _sid("e"), store, max_depth=1) is None
    assert shortest_path(_sid("a"), _sid("e"), store, max_depth=3) is not None


def test_shortest_path_rejects_zero_depth() -> None:
    store = _StubStore([])
    with pytest.raises(ValueError, match="max_depth"):
        shortest_path(_sid("a"), _sid("b"), store, max_depth=0)
