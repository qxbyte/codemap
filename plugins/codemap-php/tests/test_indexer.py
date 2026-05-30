"""Unit tests for the PHP indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_php import PhpIndexer
from codemap_php.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/User.php") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return PhpIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="php",
        ),
    )


def test_indexer_metadata() -> None:
    ix = PhpIndexer()
    assert ix.name == "php"
    assert ix.languages == ["php"]
    assert ix.supports(Path("a.php"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        <?php
        class A {}
        function f() {}
        const X = 1;
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_class_declaration() -> None:
    r = _index(
        """
        <?php
        class User {
            public string $name;
            public function hello(): string { return $this->name; }
        }
        """
    )
    classes = [s for s in r.symbols if s.kind == "class"]
    assert classes[0].extra.get("php_kind") == "class"
    methods = [s for s in r.symbols if s.kind == "method"]
    assert any("User#hello()." in str(m.id) for m in methods)
    fields = [s for s in r.symbols if s.kind == "field"]
    assert any("User#name." in str(f.id) for f in fields)


def test_interface_declaration() -> None:
    r = _index(
        """
        <?php
        interface Greeter {
            public function hello(): string;
        }
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("php_kind") == "interface"


def test_trait_declaration() -> None:
    r = _index(
        """
        <?php
        trait Loggable {
            public function log() {}
        }
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("php_kind") == "trait"


def test_namespace_captured_in_extra() -> None:
    r = _index(
        """
        <?php
        namespace App\\Models;
        class User {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert "App" in cls.extra.get("namespace", "")


def test_free_function() -> None:
    r = _index("<?php\nfunction helper(int $x): int { return $x + 1; }")
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper" in str(funcs[0].id)


def test_top_level_const_is_variable() -> None:
    r = _index("<?php\nconst MAX = 10;")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1


def test_const_inside_class_is_field() -> None:
    r = _index(
        """
        <?php
        class A {
            const DEFAULT = 1;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert any("DEFAULT" in str(f.id) for f in fields)


def test_static_method_recorded() -> None:
    r = _index(
        """
        <?php
        class User {
            public static function create(string $name): User {
                return new User();
            }
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert any("create" in str(m.id) for m in methods)


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("<?php\nclass A {}", path="src/App/A.php")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-php . . . src/App/A.php/A#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = PhpIndexer()
    r = ix.index_file(
        Path("bad.php"),
        b"\xff\xfe<?php",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.php"),
            language="php",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "PHP002"
