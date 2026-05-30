"""Unit tests for the Java indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_java import JavaIndexer
from codemap_java.indexer import SCHEME

from codemap.core.models import IndexResult
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


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = JavaIndexer()
    assert ix.name == "java"
    assert ix.languages == ["java"]
    assert "*.java" in ix.file_patterns
    assert ix.supports(Path("a.java"))
    assert not ix.supports(Path("a.kt"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        class A {
            int x;
            void m() {}
        }
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def test_class_with_method_field_constructor() -> None:
    r = _index(
        """
        class Greeter {
            String name;
            Greeter(String n) { name = n; }
            String hello() { return name; }
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert kinds == ["class", "field", "method", "method"]
    method_sigs = sorted(s.signature or "" for s in r.symbols if s.kind == "method")
    assert any("hello" in sig for sig in method_sigs)
    assert any("Greeter" in sig for sig in method_sigs)


def test_interface_marked_in_extra() -> None:
    r = _index(
        """
        interface Repo {
            void save();
        }
        """
    )
    types = [s for s in r.symbols if s.kind == "class"]
    assert len(types) == 1
    assert types[0].extra.get("java_kind") == "interface"


def test_enum_marked_in_extra() -> None:
    r = _index(
        """
        enum Color { RED, GREEN, BLUE }
        """
    )
    types = [s for s in r.symbols if s.kind == "class"]
    assert types[0].extra.get("java_kind") == "enum"


def test_record_marked_in_extra() -> None:
    r = _index("public record Point(int x, int y) {}")
    types = [s for s in r.symbols if s.kind == "class"]
    assert types[0].extra.get("java_kind") == "record"


def test_nested_class_namespacing() -> None:
    r = _index(
        """
        class Outer {
            class Inner {
                void m() {}
            }
        }
        """
    )
    ids = [str(s.id) for s in r.symbols]
    assert any("Outer#Inner#" in i for i in ids)
    assert any("Outer#Inner#m()." in i for i in ids)


def test_package_captured_in_extra() -> None:
    r = _index(
        """
        package com.example;
        class A {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("package") == "com.example"


def test_multiple_fields_in_one_decl() -> None:
    r = _index(
        """
        class A {
            int x, y, z;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert sorted(s.id.descriptors[-1].name for s in fields) == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# SymbolID + edge cases
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class A {}", path="src/com/foo/A.java")
    assert str(r.symbols[0].id) == "scip-java . . . src/com/foo/A.java/A#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = JavaIndexer()
    r = ix.index_file(
        Path("bad.java"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.java"),
            language="java",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "JAVA002"


def test_syntax_error_yields_warning() -> None:
    r = _index("class Broken { void m( ")
    codes = {d.code for d in r.diagnostics}
    assert "JAVA001" in codes


def test_method_outside_class_is_not_recorded() -> None:
    """Defensive: top-level identifiers that aren't inside a type don't
    accidentally become methods."""
    r = _index("class A {} class B { void f() {} }")
    methods = [s for s in r.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert "B#f()." in str(methods[0].id)
