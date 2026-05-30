"""Unit tests for the Ruby indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_ruby import RubyIndexer
from codemap_ruby.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "app/user.rb") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return RubyIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="ruby",
        ),
    )


def test_indexer_metadata() -> None:
    ix = RubyIndexer()
    assert ix.name == "ruby"
    assert ix.languages == ["ruby"]
    assert ix.supports(Path("a.rb"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        class A; end
        def f; end
        X = 1
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_class_declaration() -> None:
    r = _index(
        """
        class User
          def hello
            @name
          end
        end
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.extra.get("ruby_kind") == "class"
    methods = [s for s in r.symbols if s.kind == "method"]
    assert any("User#hello()." in str(m.id) for m in methods)


def test_module_declaration() -> None:
    r = _index(
        """
        module Greeter
          def hello
          end
        end
        """
    )
    mod = next(s for s in r.symbols if s.kind == "class")
    assert mod.extra.get("ruby_kind") == "module"


def test_nested_module_class_namespacing() -> None:
    r = _index(
        """
        module Outer
          class Inner
            def m
            end
          end
        end
        """
    )
    ids = [str(s.id) for s in r.symbols]
    assert any("Outer#Inner#" in i for i in ids)
    assert any("Outer#Inner#m()." in i for i in ids)


def test_singleton_method() -> None:
    r = _index(
        """
        class User
          def self.create(name)
            new(name)
          end
        end
        """
    )
    singletons = [s for s in r.symbols if s.extra.get("ruby_kind") == "singleton"]
    assert len(singletons) == 1
    assert "User#create()." in str(singletons[0].id)


def test_top_level_method_is_function() -> None:
    r = _index(
        """
        def helper(x)
          x + 1
        end
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper" in str(funcs[0].id)


def test_top_level_constant_is_variable() -> None:
    r = _index("MAX = 10")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1
    assert str(vars_[0].id).endswith("MAX.")


def test_constant_inside_class_is_field() -> None:
    r = _index(
        """
        class A
          DEFAULT = 1
        end
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert len(fields) == 1


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("class A; end", path="app/models/user.rb")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert str(cls.id) == "scip-ruby . . . app/models/user.rb/A#"


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = RubyIndexer()
    r = ix.index_file(
        Path("bad.rb"),
        b"\xff\xfe class",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.rb"),
            language="ruby",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "RB002"


def test_method_outside_type_is_function_not_method() -> None:
    r = _index("def f; end")
    funcs = [s for s in r.symbols if s.kind == "function"]
    methods = [s for s in r.symbols if s.kind == "method"]
    assert len(funcs) == 1
    assert len(methods) == 0
