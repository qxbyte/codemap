"""Unit tests for the Python cross-module call resolver bridge."""

from __future__ import annotations

from pathlib import PurePosixPath

from codemap.core.bridge.python_cross_module import PythonCrossModuleBridge
from codemap.core.models import Edge, Range, Symbol
from codemap.core.symbol import SymbolID


class _Store:
    """Minimal ReadOnlyStore for bridge tests."""

    def __init__(
        self,
        symbols: list[Symbol],
        edges: list[Edge] | None = None,
    ) -> None:
        self._symbols = {str(s.id): s for s in symbols}
        self._edges = edges or []

    def iter_symbols(self):  # type: ignore[no-untyped-def]
        return iter(self._symbols.values())

    def iter_edges(self):  # type: ignore[no-untyped-def]
        return iter(self._edges)

    def get(self, sid):  # type: ignore[no-untyped-def]
        return self._symbols.get(str(sid))

    def callers(self, sid, *, depth=1):  # pragma: no cover
        return []

    def callees(self, sid, *, depth=1):  # pragma: no cover
        return []

    def search(self, q, *, limit=10):  # pragma: no cover
        return []

    def manifest(self):  # pragma: no cover
        raise NotImplementedError


def _local_function(file: str, name: str) -> Symbol:
    return Symbol(
        id=SymbolID.parse(f"scip-python . . . {file}/{name}()."),
        kind="function",
        language="python",
        file=PurePosixPath(file),
        range=Range(start_line=1, end_line=2),
    )


def _local_class(file: str, name: str) -> Symbol:
    return Symbol(
        id=SymbolID.parse(f"scip-python . . . {file}/{name}#"),
        kind="class",
        language="python",
        file=PurePosixPath(file),
        range=Range(start_line=1, end_line=2),
    )


def _caller_in(file: str, name: str) -> SymbolID:
    return SymbolID.parse(f"scip-python . . . {file}/{name}().")


def _synthetic_target(module: str, leaf: str) -> SymbolID:
    """Mirror PythonIndexer's _external_symbol_id shape."""
    return SymbolID.parse(f"scip-python . . . {module}/{leaf}.")


def _run(symbols, edges):  # type: ignore[no-untyped-def]
    return PythonCrossModuleBridge().resolve(_Store(symbols, edges))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_resolves_unambiguous_cross_file_call() -> None:
    callee = _local_function("foo/bar.py", "helper")
    caller = _local_function("foo/baz.py", "user")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("bar", "helper"),
        kind="calls",
    )
    result = _run([callee, caller], [edge])
    assert len(result.aliases) == 1
    a = result.aliases[0]
    assert a.targets == [callee.id]
    assert a.confidence == "high"
    assert a.producer == "python_cross_module"


def test_resolves_when_namespace_matches_file_stem() -> None:
    # Two leaves with the same name but only one matches the namespace
    target_file = _local_function("pkg/wanted.py", "fn")
    decoy = _local_function("pkg/other.py", "fn")
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("wanted", "fn"),
        kind="calls",
    )
    result = _run([target_file, decoy, caller], [edge])
    assert len(result.aliases) == 1
    assert result.aliases[0].targets == [target_file.id]


def test_resolves_single_candidate_by_leaf_when_no_namespace() -> None:
    callee = _local_function("only.py", "alone")
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=SymbolID.parse("scip-python . . . alone."),  # no namespace
        kind="calls",
    )
    result = _run([callee, caller], [edge])
    assert len(result.aliases) == 1
    assert result.aliases[0].confidence == "medium"


# ---------------------------------------------------------------------------
# Skips
# ---------------------------------------------------------------------------


def test_skip_when_no_local_candidate() -> None:
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("unknown", "missing"),
        kind="calls",
    )
    result = _run([caller], [edge])
    assert result.aliases == []


def test_skip_when_multiple_candidates_match_namespace() -> None:
    a = _local_function("pkg/x.py", "fn")
    b = _local_function("pkg/x.py", "fn")  # two symbols share same path stem
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("x", "fn"),
        kind="calls",
    )
    result = _run([a, b, caller], [edge])
    # Same id should be deduplicated by the in-memory store, but if the same
    # file has two distinct names we don't pick.
    # In this constructed case ids are equal — only one symbol exists.
    # Use a different case: two files with same stem.
    a2 = _local_function("a/x.py", "fn")
    b2 = _local_function("b/x.py", "fn")
    result = _run([a2, b2, caller], [edge])
    assert result.aliases == []


def test_skip_when_target_already_resolves_locally() -> None:
    """If the edge target IS a registered symbol, leave it alone."""
    callee = _local_function("foo/bar.py", "helper")
    caller = _local_function("c.py", "use")
    edge = Edge(source=caller.id, target=callee.id, kind="calls")
    result = _run([callee, caller], [edge])
    assert result.aliases == []


def test_skip_non_python_scheme_edges() -> None:
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=SymbolID.parse("scip-typescript . . . foo.ts/bar()."),
        kind="calls",
    )
    result = _run([caller], [edge])
    assert result.aliases == []


def test_skip_non_call_edges() -> None:
    callee = _local_function("foo/bar.py", "helper")
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("bar", "helper"),
        kind="imports",
    )
    result = _run([callee, caller], [edge])
    assert result.aliases == []


def test_class_callee_is_recognised() -> None:
    callee = _local_class("foo/bar.py", "MyClass")
    caller = _local_function("c.py", "use")
    edge = Edge(
        source=caller.id,
        target=_synthetic_target("bar", "MyClass"),
        kind="calls",
    )
    result = _run([callee, caller], [edge])
    assert len(result.aliases) == 1


def test_no_double_alias_per_target() -> None:
    """Two callers both hit the same synthetic target → one alias only."""
    callee = _local_function("foo/bar.py", "helper")
    c1 = _local_function("c1.py", "user1")
    c2 = _local_function("c2.py", "user2")
    target = _synthetic_target("bar", "helper")
    edges = [
        Edge(source=c1.id, target=target, kind="calls"),
        Edge(source=c2.id, target=target, kind="calls"),
    ]
    result = _run([callee, c1, c2], edges)
    assert len(result.aliases) == 1


# ---------------------------------------------------------------------------
# Bridge metadata
# ---------------------------------------------------------------------------


def test_bridge_metadata() -> None:
    b = PythonCrossModuleBridge()
    assert b.name == "python_cross_module"
    assert b.version == "0.1.0"
    assert b.requires == []
