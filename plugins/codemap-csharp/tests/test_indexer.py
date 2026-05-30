"""Unit tests for the C# indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_csharp import CSharpIndexer
from codemap_csharp.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/Lib.cs") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return CSharpIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="csharp",
        ),
    )


def test_indexer_metadata() -> None:
    ix = CSharpIndexer()
    assert ix.name == "csharp"
    assert ix.languages == ["csharp"]
    assert ix.supports(Path("a.cs"))
    assert ix.supports(Path("a.csx"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index("class C {}")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_simple_class_with_method_field_property() -> None:
    r = _index(
        """
        class Foo {
            public int Counter;
            public string Name { get; set; }
            public void Bar() {}
        }
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    methods = [s for s in r.symbols if s.kind == "method"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {c.id.descriptors[-1].name for c in classes} == {"Foo"}
    assert {m.id.descriptors[-1].name for m in methods} == {"Bar"}
    field_names = {f.id.descriptors[-1].name for f in fields}
    assert {"Counter", "Name"} <= field_names


def test_interface_struct_record_enum_delegate() -> None:
    r = _index(
        """
        public interface IThing { void Do(); }
        public struct Point { public int X; }
        public record Person(string Name);
        public enum Color { Red, Green }
        public delegate void Handler();
        """
    )
    by_kind: dict[str, str] = {}
    for s in r.symbols:
        if s.kind == "class":
            by_kind[s.id.descriptors[-1].name] = s.extra.get("csharp_kind", "class")
    assert by_kind["IThing"] == "interface"
    assert by_kind["Point"] == "struct"
    assert by_kind["Person"] == "record"
    assert by_kind["Color"] == "enum"
    assert by_kind["Handler"] == "delegate"


def test_enum_members_emitted_as_fields() -> None:
    r = _index("enum Color { Red, Green, Blue }")
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {f.id.descriptors[-1].name for f in fields} == {"Red", "Green", "Blue"}


def test_block_namespace_prefixes_descriptors() -> None:
    r = _index(
        """
        namespace App {
            class Foo {}
        }
        """
    )
    foo = next(s for s in r.symbols if s.kind == "class")
    names = [d.name for d in foo.id.descriptors]
    assert "App" in names
    assert "Foo" in names


def test_qualified_namespace_is_split() -> None:
    r = _index(
        """
        namespace App.Core.Util {
            class Helper {}
        }
        """
    )
    helper = next(s for s in r.symbols if s.kind == "class")
    names = [d.name for d in helper.id.descriptors]
    # The three dotted components should each appear as a NAMESPACE descriptor.
    assert names.index("App") < names.index("Core") < names.index("Util") < names.index("Helper")


def test_nested_class_descriptors() -> None:
    r = _index(
        """
        class Outer {
            class Inner {
                public int Field;
            }
        }
        """
    )
    inner = next(s for s in r.symbols if s.kind == "class" and s.id.descriptors[-1].name == "Inner")
    names = [d.name for d in inner.id.descriptors]
    assert names.index("Outer") < names.index("Inner")


def test_multiple_field_declarators_on_one_line() -> None:
    r = _index(
        """
        class C {
            public int A, B, Cee;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {f.id.descriptors[-1].name for f in fields} == {"A", "B", "Cee"}


def test_property_marked_with_kind() -> None:
    r = _index(
        """
        class C {
            public string Name { get; set; }
        }
        """
    )
    name_prop = next(
        s for s in r.symbols if s.kind == "field" and s.id.descriptors[-1].name == "Name"
    )
    assert name_prop.extra.get("csharp_kind") == "property"


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class C {}", path="src/Util/Helpers.cs")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-csharp . . . src/Util/Helpers.cs/C#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = CSharpIndexer()
    r = ix.index_file(
        Path("Bad.cs"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("Bad.cs"),
            language="csharp",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "CS002"
