"""Unit tests for the Vue SFC indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_vue import VueIndexer
from codemap_vue.indexer import SCHEME
from codemap_vue.sfc import extract_script_blocks

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/App.vue") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return VueIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="vue",
        ),
    )


# ---------------------------------------------------------------------------
# SFC scanner (no parser dependency)
# ---------------------------------------------------------------------------


def test_extract_script_blocks_basic() -> None:
    src = b"<template><div/></template>\n<script>const a = 1;</script>"
    blocks = extract_script_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].lang == "js"
    assert b"const a = 1" in blocks[0].content


def test_extract_script_blocks_typescript_lang() -> None:
    src = b'<script lang="ts">const x: number = 1;</script>'
    blocks = extract_script_blocks(src)
    assert len(blocks) == 1
    assert blocks[0].lang == "ts"


def test_extract_script_blocks_setup_and_normal() -> None:
    src = (
        b'<script>export default {};</script>\n'
        b'<script setup lang="ts">const n = 1;</script>'
    )
    blocks = extract_script_blocks(src)
    assert len(blocks) == 2
    assert [b.lang for b in blocks] == ["js", "ts"]


def test_extract_script_blocks_no_script_returns_empty() -> None:
    src = b"<template><p>hi</p></template>\n<style>.x{}</style>"
    blocks = extract_script_blocks(src)
    assert blocks == []


def test_extract_script_blocks_missing_close_runs_to_eof() -> None:
    src = b"<script>const x = 1;\nconst y = 2;"  # no </script>
    blocks = extract_script_blocks(src)
    assert len(blocks) == 1
    assert b"const x" in blocks[0].content
    assert b"const y" in blocks[0].content


# ---------------------------------------------------------------------------
# Indexer metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = VueIndexer()
    assert ix.name == "vue"
    assert ix.languages == ["vue"]
    assert ix.file_patterns == ["*.vue"]
    assert ix.supports(Path("App.vue"))
    assert not ix.supports(Path("App.js"))
    assert not ix.supports(Path("App.ts"))


# ---------------------------------------------------------------------------
# Indexer: SFC content
# ---------------------------------------------------------------------------


def test_vue_with_only_template_produces_nothing() -> None:
    r = _index(
        """
        <template>
            <div>hello</div>
        </template>
        """
    )
    assert r.symbols == []


def test_vue_script_js_top_level_function() -> None:
    r = _index(
        """
        <template><div/></template>
        <script>
        function greet(name) { return name; }
        </script>
        """
    )
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "function"
    assert "greet" in str(r.symbols[0].id)


def test_vue_script_ts_top_level_class_and_method() -> None:
    """Requires the optional [typescript] extra."""
    try:
        import tree_sitter_typescript  # noqa: F401
    except ImportError:
        return  # extra not installed; skip

    r = _index(
        """
        <script lang="ts">
        export class UserService {
            login(name: string): boolean { return true; }
        }
        </script>
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert "class" in kinds
    assert "method" in kinds


def test_vue_script_setup_typescript_const() -> None:
    try:
        import tree_sitter_typescript  # noqa: F401
    except ImportError:
        return

    r = _index(
        """
        <script setup lang="ts">
        const message = 'hello';
        </script>
        """
    )
    assert any(s.kind == "variable" and "message" in str(s.id) for s in r.symbols)


def test_vue_symbol_line_numbers_account_for_template_above() -> None:
    """Symbol line numbers must be in the .vue file coordinate space."""
    r = _index(
        """
        <template>
            <div>line 2</div>
            <div>line 3</div>
            <div>line 4</div>
        </template>
        <script>
        function below() { return 1; }
        </script>
        """
    )
    fn = next(s for s in r.symbols if s.kind == "function")
    # The script block starts on a later line; ensure the symbol line is
    # not 1 (which is what a naive plug-the-script-into-an-empty-file
    # implementation would produce).
    assert fn.range is not None
    assert fn.range.start_line >= 7


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index(
        """
        <script>
        function f() {}
        </script>
        """,
        path="pkg/sub/X.vue",
    )
    ids = [str(s.id) for s in r.symbols if s.kind == "function"]
    assert any(i == "scip-vue . . . pkg/sub/X.vue/f()." for i in ids)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_invalid_utf8_yields_error_diagnostic() -> None:
    ix = VueIndexer()
    r = ix.index_file(
        Path("bad.vue"),
        b"\xff\xfe garbage",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.vue"),
            language="vue",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "VUE002"


def test_scheme_constant() -> None:
    assert SCHEME == "scip-vue"
