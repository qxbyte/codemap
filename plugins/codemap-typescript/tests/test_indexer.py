"""Unit tests for the TypeScript indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_typescript import TypeScriptIndexer
from codemap_typescript.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/m.ts") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return TypeScriptIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="typescript",
        ),
    )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = TypeScriptIndexer()
    assert ix.name == "typescript"
    assert ix.languages == ["typescript"]
    assert "*.ts" in ix.file_patterns
    assert "*.tsx" in ix.file_patterns
    assert ix.supports(Path("a.ts"))
    assert ix.supports(Path("a.tsx"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        function f() {}
        class C {}
        const X = 1;
        """
    )
    for sym in r.symbols:
        assert str(sym.id).startswith(f"{SCHEME} ")


# ---------------------------------------------------------------------------
# Top-level declarations
# ---------------------------------------------------------------------------


def test_function_declaration() -> None:
    r = _index("function hello(name: string): void { return; }")
    assert len(r.symbols) == 1
    s = r.symbols[0]
    assert s.kind == "function"
    assert "hello" in str(s.id)
    assert s.signature is not None
    assert "hello" in s.signature


def test_class_declaration_with_methods() -> None:
    r = _index(
        """
        class Greeter {
            hello(name: string): string { return name; }
            bye(): void {}
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert kinds == ["class", "method", "method"]
    method_ids = [str(s.id) for s in r.symbols if s.kind == "method"]
    assert any("Greeter#hello()." in i for i in method_ids)
    assert any("Greeter#bye()." in i for i in method_ids)


def test_interface_declaration_captured_as_class_with_extra() -> None:
    r = _index("interface User { id: number; name: string; }")
    assert len(r.symbols) == 1
    s = r.symbols[0]
    assert s.kind == "class"
    assert s.extra.get("ts_kind") == "interface"
    assert "User#" in str(s.id)


def test_top_level_const_is_variable() -> None:
    r = _index("const MAX = 10;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"
    assert str(r.symbols[0].id).endswith("MAX.")


def test_top_level_let_is_variable() -> None:
    r = _index("let counter = 0;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"


def test_top_level_multi_declarator() -> None:
    r = _index("const a = 1, b = 2;")
    assert {s.id.descriptors[-1].name for s in r.symbols} == {"a", "b"}


# ---------------------------------------------------------------------------
# SymbolID structure
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("function f() {}", path="pkg/sub/m.ts")
    assert str(r.symbols[0].id) == "scip-typescript . . . pkg/sub/m.ts/f()."


def test_tsx_file_supported() -> None:
    r = _index("function App() { return null as any; }", path="App.tsx")
    assert len(r.symbols) == 1


# ---------------------------------------------------------------------------
# Diagnostics / edge cases
# ---------------------------------------------------------------------------


def test_empty_file_produces_nothing() -> None:
    r = _index("")
    assert r.symbols == []


def test_syntax_error_yields_warning_diagnostic() -> None:
    r = _index("function broken( { ")
    codes = {d.code for d in r.diagnostics}
    assert "TS001" in codes


def test_invalid_utf8_yields_error_diagnostic() -> None:
    ix = TypeScriptIndexer()
    r = ix.index_file(
        Path("bad.ts"),
        b"\xff\xfe garbage",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.ts"),
            language="typescript",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "TS002"


# ---------------------------------------------------------------------------
# Nested classes / interfaces
# ---------------------------------------------------------------------------


def test_class_inside_function_is_skipped_as_method_path() -> None:
    """Sanity: a class declared inside a function body still produces a
    class symbol; method-stack scoping must not crash."""
    r = _index(
        """
        function outer() {
            class Inner { m() {} }
            return Inner;
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert "function" in kinds
    assert "class" in kinds
