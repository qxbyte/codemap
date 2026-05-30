"""Unit tests for the Bash indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_bash import BashIndexer
from codemap_bash.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "scripts/deploy.sh") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return BashIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="bash",
        ),
    )


def test_indexer_metadata() -> None:
    ix = BashIndexer()
    assert ix.name == "bash"
    assert ix.languages == ["bash"]
    assert ix.supports(Path("a.sh"))
    assert ix.supports(Path("a.bash"))
    assert ix.supports(Path("a.bats"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index(
        """
        FOO=1
        function f() { echo hi; }
        """
    )
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_function_definition_with_function_keyword() -> None:
    r = _index(
        """
        function greet() {
            echo "hi $1"
        }
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "greet()." in str(funcs[0].id)


def test_function_definition_without_keyword() -> None:
    r = _index(
        """
        helper() {
            local x=$1
            return 0
        }
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    assert len(funcs) == 1
    assert "helper()." in str(funcs[0].id)


def test_top_level_variable_assignment() -> None:
    r = _index("COUNT=10")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1
    assert "COUNT." in str(vars_[0].id)


def test_readonly_declaration_tagged() -> None:
    r = _index("readonly MAX_RETRIES=3")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert len(vars_) == 1
    assert vars_[0].extra.get("bash_kind") == "readonly"


def test_export_declaration_tagged() -> None:
    r = _index('export PATH_VAR="/usr/local/bin"')
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_[0].extra.get("bash_kind") == "export"


def test_declare_declaration_tagged() -> None:
    r = _index("declare -i COUNTER=0")
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_[0].extra.get("bash_kind") == "declare"


def test_function_internals_not_indexed() -> None:
    """Variables declared inside a function body are local state, not
    script-level symbols."""
    r = _index(
        """
        helper() {
            INNER_VAR=42
            local INNER_LOCAL=7
        }
        """
    )
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert vars_ == []


def test_multiple_top_level_symbols() -> None:
    r = _index(
        """
        FOO=1
        readonly BAR=2
        function f() { echo hi; }
        g() { :; }
        """
    )
    funcs = [s for s in r.symbols if s.kind == "function"]
    vars_ = [s for s in r.symbols if s.kind == "variable"]
    assert {s.id.descriptors[-1].name for s in funcs} == {"f", "g"}
    assert {s.id.descriptors[-1].name for s in vars_} == {"FOO", "BAR"}


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("FOO=1", path="scripts/utils/setup.sh")
    var = next(s for s in r.symbols if s.kind == "variable")
    assert str(var.id) == "scip-bash . . . scripts/utils/setup.sh/FOO."


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = BashIndexer()
    r = ix.index_file(
        Path("bad.sh"),
        b"\xff\xfe echo",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.sh"),
            language="bash",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "SH002"


def test_command_invocations_ignored() -> None:
    """Commands like `cp foo bar` are not symbols."""
    r = _index(
        """
        FOO=1
        cp source dest
        echo done
        """
    )
    # Only FOO should appear; commands aren't symbols.
    assert {s.id.descriptors[-1].name for s in r.symbols if s.kind == "variable"} == {"FOO"}
