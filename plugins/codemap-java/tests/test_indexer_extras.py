"""Plan 2 (rewritten) Task 1: JavaIndexer extra metadata for FQN resolver.

Indexer adds three new keys to ``Symbol.extra``:

- top-level type symbols carry ``imports`` (list[str], fully-qualified)
- top-level type symbols carry ``supertypes`` (list of {name, relation})
- method symbols carry ``pending_calls`` (list of invocation records)
"""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_java import JavaIndexer

from codemap.core.models import IndexResult, Symbol
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/Foo.java") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return JavaIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="java",
        ),
    )


def _types(result: IndexResult) -> list[Symbol]:
    return [s for s in result.symbols if s.kind == "class"]


def _methods(result: IndexResult) -> list[Symbol]:
    return [s for s in result.symbols if s.kind == "method"]


# ----- imports -----


def test_imports_recorded_on_type() -> None:
    result = _index(
        """
        package com.example;

        import java.util.List;
        import java.math.BigDecimal;
        import static java.lang.Math.max;

        public class Foo {}
        """
    )
    types = _types(result)
    assert len(types) == 1
    imports = types[0].extra["imports"]
    assert "java.util.List" in imports
    assert "java.math.BigDecimal" in imports
    assert "java.lang.Math.max" in imports


def test_wildcard_import_recorded() -> None:
    result = _index(
        """
        import java.util.*;
        public class Foo {}
        """
    )
    types = _types(result)
    assert "java.util.*" in types[0].extra["imports"]


def test_no_imports_empty_list() -> None:
    result = _index("class Foo {}")
    types = _types(result)
    assert types[0].extra.get("imports", []) == []


# ----- supertypes -----


def test_class_extends_recorded() -> None:
    result = _index("class Foo extends Bar {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "Bar", "relation": "extends"} in sup


def test_class_implements_multiple() -> None:
    result = _index("class Foo implements Iface1, Iface2 {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "Iface1", "relation": "implements"} in sup
    assert {"name": "Iface2", "relation": "implements"} in sup


def test_class_extends_and_implements() -> None:
    result = _index("class Foo extends Base implements Iface {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "Base", "relation": "extends"} in sup
    assert {"name": "Iface", "relation": "implements"} in sup


def test_interface_extends_multiple() -> None:
    result = _index("interface I extends J, K {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "J", "relation": "extends"} in sup
    assert {"name": "K", "relation": "extends"} in sup


def test_generic_supertype_strips_type_args() -> None:
    result = _index("class Foo extends Box<String, Integer> {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "Box", "relation": "extends"} in sup


def test_qualified_supertype_keeps_dots() -> None:
    result = _index("class Foo extends com.example.Base {}")
    sup = _types(result)[0].extra["supertypes"]
    assert {"name": "com.example.Base", "relation": "extends"} in sup


# ----- pending_calls -----


def test_simple_method_invocation_recorded() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                bar.greet("hi");
            }
        }
        """
    )
    methods = _methods(result)
    calls = methods[0].extra["pending_calls"]
    assert any(c["receiver"] == "bar" and c["name"] == "greet" and c["arity"] == 1 for c in calls)


def test_unqualified_invocation_has_empty_receiver() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                doIt();
            }
        }
        """
    )
    calls = _methods(result)[0].extra["pending_calls"]
    assert any(c["receiver"] == "" and c["name"] == "doIt" and c["arity"] == 0 for c in calls)


def test_static_invocation_records_class_receiver() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                Math.max(1, 2);
            }
        }
        """
    )
    calls = _methods(result)[0].extra["pending_calls"]
    assert any(c["receiver"] == "Math" and c["name"] == "max" and c["arity"] == 2 for c in calls)


def test_this_invocation_records_this_receiver() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                this.helper();
            }
        }
        """
    )
    calls = _methods(result)[0].extra["pending_calls"]
    assert any(c["receiver"] == "this" and c["name"] == "helper" for c in calls)


def test_arity_counts_each_argument() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                bar.threeArgs(1, 2, 3);
            }
        }
        """
    )
    calls = _methods(result)[0].extra["pending_calls"]
    assert any(c["name"] == "threeArgs" and c["arity"] == 3 for c in calls)


def test_chained_call_records_both_segments() -> None:
    """``foo.bar().baz()`` produces two records — outer call has the inner
    invocation as receiver (we capture the inner method name as receiver
    text so the resolver can decide whether to follow it)."""
    result = _index(
        """
        class Foo {
            void run() {
                foo.bar().baz();
            }
        }
        """
    )
    calls = _methods(result)[0].extra["pending_calls"]
    names = {c["name"] for c in calls}
    assert {"bar", "baz"} <= names


def test_call_records_location() -> None:
    result = _index(
        """
        class Foo {
            void run() {
                bar.greet();
            }
        }
        """
    )
    call = _methods(result)[0].extra["pending_calls"][0]
    assert call["line"] >= 1
    assert "col" in call


def test_method_with_no_body_has_empty_pending_calls() -> None:
    """Abstract / interface methods have no invocations."""
    result = _index(
        """
        interface I {
            void greet();
        }
        """
    )
    calls = _methods(result)[0].extra.get("pending_calls", [])
    assert calls == []


def test_constructor_invocation_records_calls_too() -> None:
    result = _index(
        """
        class Foo {
            Foo() {
                helper();
            }
        }
        """
    )
    constructors = [s for s in _methods(result) if s.id.descriptors[-1].name == "<init>"]
    assert constructors
    calls = constructors[0].extra.get("pending_calls", [])
    assert any(c["name"] == "helper" for c in calls)
