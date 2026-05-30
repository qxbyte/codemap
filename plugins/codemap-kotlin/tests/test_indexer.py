"""Unit tests for the Kotlin indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_kotlin import KotlinIndexer
from codemap_kotlin.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/Main.kt") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return KotlinIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="kotlin",
        ),
    )


def test_indexer_metadata() -> None:
    ix = KotlinIndexer()
    assert ix.name == "kotlin"
    assert ix.languages == ["kotlin"]
    assert ix.supports(Path("a.kt"))
    assert ix.supports(Path("a.kts"))
    assert not ix.supports(Path("a.java"))


def test_scheme_is_consistent() -> None:
    r = _index("class A\nfun f() {}\nval X = 1\n")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_class_declaration() -> None:
    r = _index(
        """
        class User(val name: String) {
            fun hello(): String = name
        }
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].extra.get("kotlin_kind") == "class"
    methods = [s for s in r.symbols if s.kind == "method"]
    assert any("User#hello()." in str(m.id) for m in methods)


def test_interface_kept_as_class_with_extra() -> None:
    r = _index(
        """
        interface Greeter {
            fun hello(): String
        }
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("kotlin_kind") == "interface"


def test_object_kept_as_class_with_extra() -> None:
    r = _index(
        """
        object Singleton {
            fun greet() = "hi"
        }
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("kotlin_kind") == "object"


def test_package_captured_in_extra() -> None:
    r = _index(
        """
        package com.example
        class A
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("package") == "com.example"


def test_free_function() -> None:
    r = _index("fun helper(x: Int): Int = x + 1")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper" in str(funcs[0].id)


def test_top_level_val_is_variable() -> None:
    r = _index("val MAX = 10")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1


def test_top_level_var_is_variable() -> None:
    r = _index("var counter = 0")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1


def test_method_inside_class_uses_method_kind() -> None:
    r = _index(
        """
        class User {
            fun hello() = ""
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(methods) == 1
    assert len(funcs) == 0


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class A", path="src/main/kotlin/A.kt")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-kotlin . . . src/main/kotlin/A.kt/A#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = KotlinIndexer()
    r = ix.index_file(
        Path("bad.kt"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.kt"),
            language="kotlin",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "KT002"


def test_kts_extension_supported() -> None:
    r = _index("fun main() {}", path="build.kts")
    assert any(s.kind == "function" for s in r.symbols)
