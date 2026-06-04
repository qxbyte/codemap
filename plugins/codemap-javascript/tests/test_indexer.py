"""Unit tests for the JavaScript indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_javascript import JavaScriptIndexer
from codemap_javascript.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/m.js") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return JavaScriptIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="javascript",
        ),
    )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = JavaScriptIndexer()
    assert ix.name == "javascript"
    assert ix.languages == ["javascript"]
    assert set(ix.file_patterns) == {"*.js", "*.jsx", "*.mjs", "*.cjs"}
    assert ix.supports(Path("a.js"))
    assert ix.supports(Path("a.jsx"))
    assert ix.supports(Path("a.mjs"))
    assert ix.supports(Path("a.cjs"))
    assert not ix.supports(Path("a.ts"))
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
    r = _index("function hello(name) { return name; }")
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
            hello(name) { return name; }
            bye() {}
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert kinds == ["class", "method", "method"]
    method_ids = [str(s.id) for s in r.symbols if s.kind == "method"]
    assert any("Greeter#hello()." in i for i in method_ids)
    assert any("Greeter#bye()." in i for i in method_ids)


def test_top_level_const_is_variable() -> None:
    r = _index("const MAX = 10;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"
    assert str(r.symbols[0].id).endswith("MAX.")


def test_top_level_let_is_variable() -> None:
    r = _index("let counter = 0;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"


def test_top_level_var_is_variable() -> None:
    r = _index("var legacy = 1;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"


def test_top_level_multi_declarator() -> None:
    r = _index("const a = 1, b = 2;")
    assert {s.id.descriptors[-1].name for s in r.symbols} == {"a", "b"}


# ---------------------------------------------------------------------------
# SymbolID structure
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("function f() {}", path="pkg/sub/m.js")
    assert str(r.symbols[0].id) == "scip-javascript . . . pkg/sub/m.js/f()."


def test_jsx_file_supported() -> None:
    r = _index(
        """
        function App() {
            return <div>hello</div>;
        }
        """,
        path="App.jsx",
    )
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "function"


def test_mjs_module_supported() -> None:
    r = _index(
        """
        export function fromEsm() { return 1; }
        """,
        path="lib.mjs",
    )
    assert any(s.kind == "function" and "fromEsm" in str(s.id) for s in r.symbols)


def test_cjs_module_supported() -> None:
    r = _index(
        """
        function fromCjs() { return 1; }
        module.exports = { fromCjs };
        """,
        path="lib.cjs",
    )
    assert any(s.kind == "function" and "fromCjs" in str(s.id) for s in r.symbols)


# ---------------------------------------------------------------------------
# Diagnostics / edge cases
# ---------------------------------------------------------------------------


def test_empty_file_produces_nothing() -> None:
    r = _index("")
    assert r.symbols == []


def test_syntax_error_yields_warning_diagnostic() -> None:
    r = _index("function broken( { ")
    codes = {d.code for d in r.diagnostics}
    assert "JS001" in codes


def test_invalid_utf8_yields_error_diagnostic() -> None:
    ix = JavaScriptIndexer()
    r = ix.index_file(
        Path("bad.js"),
        b"\xff\xfe garbage",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.js"),
            language="javascript",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "JS002"


# ---------------------------------------------------------------------------
# Nested classes
# ---------------------------------------------------------------------------


def test_class_inside_function_is_still_indexed() -> None:
    r = _index(
        """
        function outer() {
            class Inner {
                m() {}
            }
            return Inner;
        }
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert "function" in kinds
    assert "class" in kinds


# ---------------------------------------------------------------------------
# Arrow functions / object methods (not currently indexed — sanity only)
# ---------------------------------------------------------------------------


def test_arrow_function_not_indexed_at_top_level() -> None:
    """Top-level ``const fn = () => ...`` is a variable, not a function.

    Matching the typescript indexer's behavior: arrows assigned to consts
    surface as variables, not functions. A future PR may add named arrow
    detection across both plugins.
    """
    r = _index("const add = (a, b) => a + b;")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"
