"""Unit tests for the Go indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_go import GoIndexer
from codemap_go.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "main.go") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return GoIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="go",
        ),
    )


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = GoIndexer()
    assert ix.name == "go"
    assert ix.languages == ["go"]
    assert "*.go" in ix.file_patterns
    assert ix.supports(Path("a.go"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        package main
        func f() {}
        type T struct {}
        const C = 1
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


# ---------------------------------------------------------------------------
# Functions / methods
# ---------------------------------------------------------------------------


def test_function_declaration() -> None:
    r = _index(
        """
        package main
        func helper(x int) int { return x + 1 }
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper" in str(funcs[0].id)
    assert funcs[0].extra.get("package") == "main"


def test_method_attached_to_receiver_value() -> None:
    r = _index(
        """
        package main
        type User struct { Name string }
        func (u User) Hello() string { return u.Name }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert len(methods) == 1
    assert "User#Hello()." in str(methods[0].id)
    assert methods[0].extra.get("receiver_type") == "User"


def test_method_attached_to_pointer_receiver() -> None:
    r = _index(
        """
        package main
        type User struct {}
        func (u *User) Login(pw string) bool { return false }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert "User#Login()." in str(methods[0].id)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


def test_struct_type() -> None:
    r = _index("package main\ntype User struct { ID int }")
    types = [s for s in r.symbols if s.kind == "class"]
    assert len(types) == 1
    assert types[0].extra.get("go_kind") == "struct"


def test_interface_type() -> None:
    r = _index(
        """
        package main
        type Greeter interface { Hello() string }
        """
    )
    types = [s for s in r.symbols if s.kind == "class"]
    assert types[0].extra.get("go_kind") == "interface"


# ---------------------------------------------------------------------------
# Constants / variables
# ---------------------------------------------------------------------------


def test_const_declaration() -> None:
    r = _index("package main\nconst MAX = 10")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1
    assert vars_[0].extra.get("go_kind") == "const"


def test_var_declaration() -> None:
    r = _index("package main\nvar counter int")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_[0].extra.get("go_kind") == "var"


# ---------------------------------------------------------------------------
# SymbolID + edge cases
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index(
        "package user\nfunc helper() {}",
        path="pkg/user/u.go",
    )
    assert str(r.symbols[0].id) == "scip-go . . . pkg/user/u.go/helper()."


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = GoIndexer()
    r = ix.index_file(
        Path("bad.go"),
        b"\xff\xfe package",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.go"),
            language="go",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "GO002"


def test_package_captured_on_symbols() -> None:
    r = _index(
        """
        package user
        type User struct {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("package") == "user"
