"""Plan 2 Task 2: JavaCallResolverBridge."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from codemap_java import JavaIndexer
from codemap_java.resolver import JavaCallResolverBridge

from codemap.core.models import Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

# ---------------------------------------------------------------------------
# Stub ReadOnlyStore
# ---------------------------------------------------------------------------


class _StubStore:
    def __init__(self, symbols: list[Symbol]) -> None:
        self._symbols = symbols

    def iter_symbols(self):  # type: ignore[no-untyped-def]
        return iter(self._symbols)

    def get(self, sid):  # pragma: no cover
        return None

    def iter_edges(self):  # pragma: no cover
        return iter([])

    def callers(self, sid, *, depth=1):  # pragma: no cover
        return []

    def callees(self, sid, *, depth=1):  # pragma: no cover
        return []

    def search(self, query, *, limit=10):  # pragma: no cover
        return []

    def manifest(self):  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers — directly build store from indexer output
# ---------------------------------------------------------------------------


def _index(source: str, *, rel_path: str) -> list[Symbol]:
    res = JavaIndexer().index_file(
        Path(f"/tmp/{rel_path}"),
        source.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp"),
            relative_path=PurePosixPath(rel_path),
            language="java",
        ),
    )
    return list(res.symbols)


def _has_edge(edges, src_name: str, tgt_name: str, kind: str) -> bool:
    return any(
        e.kind == kind
        and e.source.descriptors[-1].name == src_name
        and e.target.descriptors[-1].name == tgt_name
        for e in edges
    )


# ---------------------------------------------------------------------------
# Bridge metadata
# ---------------------------------------------------------------------------


def test_bridge_metadata() -> None:
    b = JavaCallResolverBridge()
    assert b.name == "java_calls"
    assert hasattr(b, "version")


# ---------------------------------------------------------------------------
# Same-class call (unqualified / this)
# ---------------------------------------------------------------------------


def test_unqualified_call_resolves_to_same_class_method() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void run() { helper(); }
            void helper() {}
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    assert _has_edge(result.edges, "run", "helper", "calls")


def test_this_call_resolves_to_same_class_method() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void run() { this.helper(); }
            void helper() {}
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    assert _has_edge(result.edges, "run", "helper", "calls")


# ---------------------------------------------------------------------------
# Field receiver — cross-class via field type
# ---------------------------------------------------------------------------


def test_field_call_resolves_via_field_type_same_package() -> None:
    syms = []
    syms += _index(
        """
        package com.example;
        public class OrderService {
            private final CouponMapper couponMapper = null;
            public int calcPrice(long userId) {
                return couponMapper.selectByUser(userId);
            }
        }
        """,
        rel_path="src/com/example/OrderService.java",
    )
    syms += _index(
        """
        package com.example;
        public interface CouponMapper {
            int selectByUser(long userId);
        }
        """,
        rel_path="src/com/example/CouponMapper.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(syms))
    assert _has_edge(result.edges, "calcPrice", "selectByUser", "calls")


def test_field_call_resolves_via_imported_type() -> None:
    syms = []
    syms += _index(
        """
        package com.example.svc;
        import com.example.mapper.CouponMapper;
        public class OrderService {
            private CouponMapper couponMapper;
            public int calcPrice() { return couponMapper.selectByUser(1L); }
        }
        """,
        rel_path="src/com/example/svc/OrderService.java",
    )
    syms += _index(
        """
        package com.example.mapper;
        public interface CouponMapper {
            int selectByUser(long userId);
        }
        """,
        rel_path="src/com/example/mapper/CouponMapper.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(syms))
    assert _has_edge(result.edges, "calcPrice", "selectByUser", "calls")


# ---------------------------------------------------------------------------
# extends / implements edges
# ---------------------------------------------------------------------------


def test_extends_edge_same_package() -> None:
    syms = []
    syms += _index(
        "package a; public class Base {}",
        rel_path="src/a/Base.java",
    )
    syms += _index(
        "package a; public class Sub extends Base {}",
        rel_path="src/a/Sub.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(syms))
    assert _has_edge(result.edges, "Sub", "Base", "extends")


def test_implements_edge_via_import() -> None:
    syms = []
    syms += _index(
        "package a.iface; public interface Animal {}",
        rel_path="src/a/iface/Animal.java",
    )
    syms += _index(
        """
        package b;
        import a.iface.Animal;
        public class Dog implements Animal {}
        """,
        rel_path="src/b/Dog.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(syms))
    assert _has_edge(result.edges, "Dog", "Animal", "implements")


def test_extends_supertype_unresolved_no_edge() -> None:
    syms = _index(
        "package a; public class Foo extends ThirdParty {}",
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(syms))
    assert not any(e.kind in {"extends", "implements"} for e in result.edges)


# ---------------------------------------------------------------------------
# Arity matters — overload disambiguation
# ---------------------------------------------------------------------------


def test_overload_by_arity() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void greet() {}
            void greet(String n) {}
            void run() { greet("hi"); }
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    # The 1-arity greet should be the call target.
    calls_to_greet = [
        e
        for e in result.edges
        if e.kind == "calls"
        and e.source.descriptors[-1].name == "run"
        and e.target.descriptors[-1].name == "greet"
    ]
    assert len(calls_to_greet) == 1
    # We can't introspect arity from the SymbolID directly, but the bridge
    # picks at most one method for matching arity — verifying exactly one
    # edge confirms the disambiguation worked (otherwise we'd see two).


def test_arity_mismatch_no_edge() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void greet(String n) {}
            void run() { greet(); }    // 0 args, only 1-arity exists
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    assert not _has_edge(result.edges, "run", "greet", "calls")


# ---------------------------------------------------------------------------
# Confidence + diagnostics
# ---------------------------------------------------------------------------


def test_edges_are_medium_confidence() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void run() { helper(); }
            void helper() {}
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    assert all(e.confidence == "medium" for e in result.edges if e.kind == "calls")


def test_unresolved_call_does_not_build_edge_and_does_not_crash() -> None:
    symbols = _index(
        """
        package a;
        class Foo {
            void run() { unknownObj.unknownMethod(); }
        }
        """,
        rel_path="src/a/Foo.java",
    )
    result = JavaCallResolverBridge().resolve(_StubStore(symbols))
    assert not any(e.target.descriptors[-1].name == "unknownMethod" for e in result.edges)


# ---------------------------------------------------------------------------
# Non-Java symbols are ignored
# ---------------------------------------------------------------------------


def test_non_java_symbols_ignored() -> None:
    py_sym = Symbol(
        id=SymbolID(
            scheme="scip-python",
            descriptors=(Descriptor(name="foo", kind=DescriptorKind.METHOD),),
        ),
        kind="method",
        language="python",
        file=PurePosixPath("a.py"),
        range=Range(start_line=1, end_line=1),
        extra={"pending_calls": [{"receiver": "", "name": "bar", "arity": 0, "line": 1, "col": 0}]},
    )
    result = JavaCallResolverBridge().resolve(_StubStore([py_sym]))
    assert result.edges == []
