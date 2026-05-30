"""Unit tests for the C++ indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_cpp import CppIndexer
from codemap_cpp.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/lib.cpp") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return CppIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="cpp",
        ),
    )


def test_indexer_metadata() -> None:
    ix = CppIndexer()
    assert ix.name == "cpp"
    assert ix.languages == ["cpp"]
    for ext in (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"):
        assert ix.supports(Path(f"a{ext}"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index("int x = 1; int f() { return 0; }")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_free_function() -> None:
    r = _index("int add(int a, int b) { return a + b; }")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert funcs[0].id.descriptors[-1].name == "add"


def test_class_with_method_and_field() -> None:
    r = _index(
        """
        class Foo {
            int counter;
            void bar() {}
        };
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    methods = [s for s in r.symbols if s.kind == "method"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert len(classes) == 1
    assert classes[0].extra["cpp_kind"] == "class"
    assert {m.id.descriptors[-1].name for m in methods} == {"bar"}
    assert {f.id.descriptors[-1].name for f in fields} == {"counter"}


def test_struct_treated_as_class() -> None:
    r = _index(
        """
        struct Point {
            int x;
            int y;
        };
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra["cpp_kind"] == "struct"


def test_enum_class_with_enumerators() -> None:
    r = _index("enum class Color { RED, GREEN };")
    classes = [s for s in r.symbols if s.kind == "class"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert classes[0].extra["cpp_kind"] == "enum"
    assert {f.id.descriptors[-1].name for f in fields} == {"RED", "GREEN"}


def test_namespace_prefixes_descriptors() -> None:
    r = _index(
        """
        namespace ns {
            int gx = 1;
            class Foo {
                int bar;
            };
        }
        """
    )
    # The outer namespace should appear as a NAMESPACE descriptor on
    # Foo's symbol id.
    foo = next(s for s in r.symbols if s.kind == "class")
    name_chain = [d.name for d in foo.id.descriptors]
    assert "ns" in name_chain
    assert "Foo" in name_chain


def test_nested_namespace_chain() -> None:
    r = _index(
        """
        namespace outer {
            namespace inner {
                int compute() { return 0; }
            }
        }
        """
    )
    compute = next(s for s in r.symbols if s.kind == "function")
    name_chain = [d.name for d in compute.id.descriptors]
    # outer and inner appear before compute().
    assert name_chain.index("outer") < name_chain.index("inner") < name_chain.index("compute")


def test_template_function_unwrapped() -> None:
    r = _index(
        """
        template<typename T>
        T identity(T value) { return value; }
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert {f.id.descriptors[-1].name for f in funcs} == {"identity"}


def test_template_class_unwrapped() -> None:
    r = _index(
        """
        template<typename T>
        class Box {
            T value;
        };
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    assert {c.id.descriptors[-1].name for c in classes} == {"Box"}


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("int x = 1;", path="src/util/math.cpp")
    # Top-level declarations without init are not emitted; need a class for path test.
    r = _index("struct S { int x; };", path="src/util/math.cpp")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-cpp . . . src/util/math.cpp/S#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = CppIndexer()
    r = ix.index_file(
        Path("bad.cpp"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.cpp"),
            language="cpp",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "CPP002"
