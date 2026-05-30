"""Unit tests for the Swift indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_swift import SwiftIndexer
from codemap_swift.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/Main.swift") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return SwiftIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="swift",
        ),
    )


def test_indexer_metadata() -> None:
    ix = SwiftIndexer()
    assert ix.name == "swift"
    assert ix.languages == ["swift"]
    assert ix.supports(Path("a.swift"))
    assert not ix.supports(Path("a.kt"))


def test_scheme_is_consistent() -> None:
    r = _index("class A {}\nfunc f() {}\nlet X = 1\n")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_class_declaration() -> None:
    r = _index(
        """
        class User {
            var name: String = ""
            func hello() -> String { return name }
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert kinds == ["class", "field", "method"]
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("swift_kind") == "class"


def test_struct_kept_as_class_with_extra() -> None:
    r = _index("struct Point { let x: Int; let y: Int }")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("swift_kind") == "struct"


def test_enum_kept_as_class_with_extra() -> None:
    r = _index("enum Color { case red, green, blue }")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("swift_kind") == "enum"


def test_protocol_kept_as_class_with_extra() -> None:
    r = _index(
        """
        protocol Greeter {
            func hello() -> String
        }
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("swift_kind") == "protocol"


def test_init_inside_class() -> None:
    r = _index(
        """
        class User {
            var name: String
            init(name: String) { self.name = name }
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert any("init" in str(m.id) for m in methods)


def test_free_function() -> None:
    r = _index("func helper(x: Int) -> Int { return x + 1 }")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper" in str(funcs[0].id)


def test_top_level_let_is_variable() -> None:
    r = _index("let MAX = 10")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1


def test_top_level_var_is_variable() -> None:
    r = _index("var counter = 0")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1


def test_method_inside_class_attaches_to_type() -> None:
    r = _index(
        """
        class User {
            func hello() -> String { return "" }
        }
        """
    )
    method = next(s for s in r.symbols if s.kind == "method")
    assert "User#hello()." in str(method.id)


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class A {}", path="src/Foo/Bar.swift")
    assert str(next(s for s in r.symbols if s.kind == "class").id) == (
        "scip-swift . . . src/Foo/Bar.swift/A#"
    )


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = SwiftIndexer()
    r = ix.index_file(
        Path("bad.swift"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.swift"),
            language="swift",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "SW002"
