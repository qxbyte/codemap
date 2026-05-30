"""Unit tests for the Rust indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_rust import RustIndexer
from codemap_rust.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/lib.rs") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return RustIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="rust",
        ),
    )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = RustIndexer()
    assert ix.name == "rust"
    assert ix.languages == ["rust"]
    assert ix.supports(Path("a.rs"))
    assert not ix.supports(Path("a.go"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        fn f() {}
        struct S;
        const C: u32 = 1;
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


# ---------------------------------------------------------------------------
# Function / impl
# ---------------------------------------------------------------------------


def test_free_function() -> None:
    r = _index("fn helper(x: u32) -> u32 { x + 1 }")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper()." in str(funcs[0].id)


def test_inherent_impl_method_attaches_to_type() -> None:
    r = _index(
        """
        struct User;
        impl User {
            fn new() -> Self { User }
            fn login(&mut self) -> bool { false }
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    method_ids = {str(s.id) for s in methods}
    assert any("User#new()." in i for i in method_ids)
    assert any("User#login()." in i for i in method_ids)


def test_trait_impl_method_attaches_to_receiver_type() -> None:
    r = _index(
        """
        trait Greeter { fn hello(&self) -> String; }
        struct User;
        impl Greeter for User {
            fn hello(&self) -> String { String::new() }
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    # User#hello (impl) + Greeter#hello (trait signature) → 2 methods
    ids = {str(s.id) for s in methods}
    assert any("User#hello()." in i for i in ids)
    assert any("Greeter#hello()." in i for i in ids)


# ---------------------------------------------------------------------------
# Type-level items
# ---------------------------------------------------------------------------


def test_struct_decl() -> None:
    r = _index("struct User { id: u32 }")
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra.get("rust_kind") == "struct"


def test_enum_decl() -> None:
    r = _index("enum Color { Red, Green, Blue }")
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra.get("rust_kind") == "enum"


def test_trait_decl() -> None:
    r = _index("trait Greeter { fn hello(&self) -> String; }")
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra.get("rust_kind") == "trait"


# ---------------------------------------------------------------------------
# Const / static
# ---------------------------------------------------------------------------


def test_const_decl() -> None:
    r = _index("const MAX: u32 = 10;")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_[0].extra.get("rust_kind") == "const"


def test_static_decl() -> None:
    r = _index("static COUNTER: u32 = 0;")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_[0].extra.get("rust_kind") == "static"


# ---------------------------------------------------------------------------
# SymbolID + edge cases
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("fn helper() {}", path="src/user.rs")
    assert str(r.symbols[0].id) == "scip-rust . . . src/user.rs/helper()."


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = RustIndexer()
    r = ix.index_file(
        Path("bad.rs"),
        b"\xff\xfe fn",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.rs"),
            language="rust",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "RS002"
