"""Unit tests for the C indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_c import CIndexer
from codemap_c.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/lib.c") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return CIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="c",
        ),
    )


def test_indexer_metadata() -> None:
    ix = CIndexer()
    assert ix.name == "c"
    assert ix.languages == ["c"]
    assert ix.supports(Path("a.c"))
    assert ix.supports(Path("a.h"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index("int x = 1;\nint f(void) { return 0; }")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_function_definition() -> None:
    r = _index("int add(int a, int b) { return a + b; }")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert funcs[0].id.descriptors[-1].name == "add"
    assert funcs[0].signature == "add()"


def test_struct_with_fields() -> None:
    r = _index(
        """
        struct Point {
            int x;
            int y;
        };
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert len(classes) == 1
    assert classes[0].extra["c_kind"] == "struct"
    assert {f.id.descriptors[-1].name for f in fields} == {"x", "y"}


def test_union_with_fields() -> None:
    r = _index(
        """
        union U {
            int i;
            float f;
        };
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].extra["c_kind"] == "union"
    assert len([s for s in r.symbols if s.kind == "field"]) == 2


def test_enum_with_enumerators() -> None:
    r = _index("enum Color { RED, GREEN, BLUE };")
    classes = [s for s in r.symbols if s.kind == "class"]
    fields = [s for s in r.symbols if s.kind == "field"]
    assert classes[0].extra["c_kind"] == "enum"
    assert {f.id.descriptors[-1].name for f in fields} == {"RED", "GREEN", "BLUE"}


def test_typedef_int_alias() -> None:
    r = _index("typedef int MyInt;")
    typedefs = [s for s in r.symbols if s.kind == "class"]
    assert len(typedefs) == 1
    assert typedefs[0].extra["c_kind"] == "typedef"
    assert typedefs[0].id.descriptors[-1].name == "MyInt"


def test_object_macro() -> None:
    r = _index("#define MAX 10")
    macros = [s for s in r.symbols if s.kind == "variable"]
    assert len(macros) == 1
    assert macros[0].extra["c_kind"] == "macro"
    assert macros[0].id.descriptors[-1].name == "MAX"


def test_function_like_macro() -> None:
    r = _index("#define SQUARE(x) ((x)*(x))")
    macros = [s for s in r.symbols if s.kind == "variable"]
    assert macros[0].extra["c_kind"] == "macro_fn"
    assert macros[0].id.descriptors[-1].name == "SQUARE"


def test_top_level_variable_with_initializer() -> None:
    r = _index("static int counter = 0;")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1
    assert vars_[0].id.descriptors[-1].name == "counter"


def test_function_bodies_are_opaque() -> None:
    """Locals declared inside a function body must not surface."""
    r = _index(
        """
        int compute(void) {
            int local_a = 1;
            int local_b = 2;
            return local_a + local_b;
        }
        """
    )
    assert {s.id.descriptors[-1].name for s in r.symbols} == {"compute"}


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("int x = 1;", path="src/util/math.c")
    var = next(s for s in r.symbols if s.kind == "variable")
    assert str(var.id) == "scip-c . . . src/util/math.c/x."


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = CIndexer()
    r = ix.index_file(
        Path("bad.c"),
        b"\xff\xfe int",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.c"),
            language="c",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "C002"


def test_realistic_translation_unit() -> None:
    r = _index(
        """
        #include <stdio.h>
        #define MAX 100
        typedef struct { int x; } Box;
        struct Inner { int v; };
        enum Mode { ON, OFF };
        static int counter = 0;
        int process(int n) { return n + counter; }
        """
    )
    by_kind: dict[str, set[str]] = {}
    for s in r.symbols:
        by_kind.setdefault(s.kind, set()).add(s.id.descriptors[-1].name)
    assert "process" in by_kind["function"]
    assert {"MAX", "counter"} <= by_kind["variable"]
    assert {"Box", "Inner", "Mode"} <= by_kind["class"]
    # Fields inside anonymous struct under a typedef are not addressable
    # by C name scoping; only named-struct fields surface.
    assert {"v", "ON", "OFF"} <= by_kind["field"]
