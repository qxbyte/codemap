"""Unit tests for the Scala indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_scala import ScalaIndexer
from codemap_scala.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/Lib.scala") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return ScalaIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="scala",
        ),
    )


def test_indexer_metadata() -> None:
    ix = ScalaIndexer()
    assert ix.name == "scala"
    assert ix.languages == ["scala"]
    assert ix.supports(Path("a.scala"))
    assert ix.supports(Path("a.sc"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index("class C")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_class_with_val_var_def() -> None:
    r = _index(
        """
        class Foo {
          val x: Int = 1
          var y: String = "hi"
          def bar(a: Int): Int = a + 1
        }
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    methods = [s for s in r.symbols if s.kind == "method"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {c.id.descriptors[-1].name for c in classes} == {"Foo"}
    assert {m.id.descriptors[-1].name for m in methods} == {"bar"}
    assert {f.id.descriptors[-1].name for f in fields} == {"x", "y"}
    val_field = next(f for f in fields if f.id.descriptors[-1].name == "x")
    var_field = next(f for f in fields if f.id.descriptors[-1].name == "y")
    assert val_field.extra["scala_kind"] == "val"
    assert var_field.extra["scala_kind"] == "var"


def test_object_definition() -> None:
    r = _index(
        """
        object Helpers {
          def hello = "world"
        }
        """
    )
    obj = next(s for s in r.symbols if s.kind == "class")
    assert obj.extra["scala_kind"] == "object"
    methods = [s for s in r.symbols if s.kind == "method"]
    assert {m.id.descriptors[-1].name for m in methods} == {"hello"}


def test_trait_with_function_declaration() -> None:
    r = _index(
        """
        trait Greeter {
          def greet: String
        }
        """
    )
    trait = next(s for s in r.symbols if s.kind == "class")
    assert trait.extra["scala_kind"] == "trait"
    methods = [s for s in r.symbols if s.kind == "method"]
    assert {m.id.descriptors[-1].name for m in methods} == {"greet"}


def test_case_class_parameters_become_fields() -> None:
    r = _index("case class Person(name: String, age: Int)")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra["scala_kind"] == "case_class"
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {f.id.descriptors[-1].name for f in fields} == {"name", "age"}
    for f in fields:
        assert f.extra["scala_kind"] == "case_field"


def test_top_level_type_alias() -> None:
    r = _index("type Aliased = Int")
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra["scala_kind"] == "type"
    assert classes[0].id.descriptors[-1].name == "Aliased"


def test_package_clause_prefixes_descriptors() -> None:
    r = _index(
        """
        package com.example.app
        class Foo
        """
    )
    foo = next(s for s in r.symbols if s.kind == "class")
    names = [d.name for d in foo.id.descriptors]
    assert names.index("com") < names.index("example") < names.index("app") < names.index("Foo")


def test_nested_class_in_object() -> None:
    r = _index(
        """
        object Outer {
          class Inner {
            val a: Int = 1
          }
        }
        """
    )
    inner = next(s for s in r.symbols if s.kind == "class" and s.id.descriptors[-1].name == "Inner")
    names = [d.name for d in inner.id.descriptors]
    assert names.index("Outer") < names.index("Inner")


def test_top_level_val_and_def() -> None:
    r = _index(
        """
        val greeting = "hi"
        def shout(s: String): String = s.toUpperCase
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    methods = [s for s in r.symbols if s.kind == "method"]
    assert {f.id.descriptors[-1].name for f in fields} == {"greeting"}
    assert {m.id.descriptors[-1].name for m in methods} == {"shout"}


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class C", path="src/util/Helpers.scala")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-scala . . . src/util/Helpers.scala/C#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = ScalaIndexer()
    r = ix.index_file(
        Path("Bad.scala"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("Bad.scala"),
            language="scala",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "SCALA002"
