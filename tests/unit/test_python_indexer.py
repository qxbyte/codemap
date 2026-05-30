"""Unit tests for ``codemap.indexers.python.PythonIndexer``.

Focused on AST → symbol / edge mapping correctness on small inline inputs.
Golden directory fixtures live in ``tests/fixtures/indexers/python``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

import pytest

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext
from codemap.indexers.python import SCHEME, PythonIndexer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index(source: str, *, path: str = "src/foo.py") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return PythonIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="python",
        ),
    )


def _symbol_ids(result: IndexResult) -> list[str]:
    return [str(s.id) for s in result.symbols]


def _edge_pairs(result: IndexResult) -> list[tuple[str, str, str]]:
    return [(str(e.source), str(e.target), e.kind) for e in result.edges]


# ---------------------------------------------------------------------------
# Top-level definitions
# ---------------------------------------------------------------------------


def test_top_level_function() -> None:
    r = _index(
        """
        def hello(name: str) -> str:
            return f"hi {name}"
        """
    )
    assert len(r.symbols) == 1
    sym = r.symbols[0]
    assert sym.kind == "function"
    assert sym.language == "python"
    assert sym.signature == "def hello(name: str)"
    assert "scip-python" in str(sym.id)
    assert "hello()" in str(sym.id)


def test_async_function_marked_in_extra() -> None:
    r = _index("async def fetch():\n    pass\n")
    assert r.symbols[0].extra == {"async": True}
    assert r.symbols[0].signature.startswith("async def fetch")


def test_module_level_variable() -> None:
    r = _index("MAX_RETRIES = 5\n")
    assert len(r.symbols) == 1
    assert r.symbols[0].kind == "variable"
    assert str(r.symbols[0].id).endswith("MAX_RETRIES.")


def test_class_with_methods() -> None:
    r = _index(
        """
        class Foo:
            def bar(self):
                pass

            async def baz(self):
                pass
        """
    )
    kinds = [(s.kind, str(s.id).split("/")[-1]) for s in r.symbols]
    assert ("class", "Foo#") in kinds
    method_ids = [s for s in r.symbols if s.kind == "method"]
    assert {m.signature for m in method_ids} == {
        "def bar(self)",
        "async def baz(self)",
    }


def test_class_field_assignment() -> None:
    r = _index(
        """
        class Foo:
            CONST = 42
            def bar(self):
                pass
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert kinds == ["class", "field", "method"]


def test_function_inside_class_is_method() -> None:
    r = _index(
        """
        class A:
            def m(self): pass
        def f(): pass
        """
    )
    kinds = {s.kind for s in r.symbols}
    assert "method" in kinds
    assert "function" in kinds


def test_nested_class_namespacing() -> None:
    r = _index(
        """
        class Outer:
            class Inner:
                def m(self): pass
        """
    )
    ids = _symbol_ids(r)
    assert any("Outer#Inner#" in i for i in ids)
    assert any("Outer#Inner#m()" in i for i in ids)


def test_decorators_captured() -> None:
    r = _index(
        """
        @staticmethod
        @cache
        def foo(): pass
        """
    )
    assert r.symbols[0].extra.get("decorators") == ["staticmethod", "cache"]


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def test_top_level_import_does_not_emit_edge() -> None:
    """Top-level ``import`` lives outside any callable, so no edge has a
    valid ``source``. The import table still updates so subsequent calls
    can resolve through it (covered by ``test_call_to_imported_name``).
    """
    r = _index("import os\n")
    assert [e for e in r.edges if e.kind == "imports"] == []


def test_import_inside_function_emits_edge() -> None:
    r = _index(
        """
        def f():
            import json
            json.dumps({})
        """
    )
    import_edges = [e for e in r.edges if e.kind == "imports"]
    assert len(import_edges) == 1
    assert "json" in str(import_edges[0].target)


def test_from_import_inside_function_emits_edge() -> None:
    r = _index(
        """
        def f():
            from collections import defaultdict
            defaultdict(list)
        """
    )
    import_edges = [e for e in r.edges if e.kind == "imports"]
    assert len(import_edges) == 1
    assert "collections" in str(import_edges[0].target)


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


def test_same_file_call_edge() -> None:
    r = _index(
        """
        def callee(): pass

        def caller():
            callee()
        """
    )
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 1
    pair = call_edges[0]
    assert "caller()" in str(pair.source)
    assert "callee()" in str(pair.target)
    assert pair.confidence == "high"


def test_call_to_imported_name() -> None:
    r = _index(
        """
        from foo import bar

        def use():
            bar()
        """
    )
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 1
    target = str(call_edges[0].target)
    # The target is a scip-python symbol pointing at module ``foo`` term ``bar``
    assert "scip-python" in target
    assert "foo" in target


def test_call_to_unknown_falls_back_to_local_scheme() -> None:
    r = _index(
        """
        def use():
            mystery()
        """
    )
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 1
    assert str(call_edges[0].target).startswith("local ")


def test_no_call_edge_at_module_level() -> None:
    """Calls at module-level have no enclosing callable, so no edge is emitted."""
    r = _index("print('hi')\n")
    assert [e for e in r.edges if e.kind == "calls"] == []


# ---------------------------------------------------------------------------
# Class inheritance
# ---------------------------------------------------------------------------


def test_extends_edge_for_local_base() -> None:
    r = _index(
        """
        class Base: pass

        class Sub(Base): pass
        """
    )
    extends = [e for e in r.edges if e.kind == "extends"]
    assert len(extends) == 1
    assert "Sub#" in str(extends[0].source)
    assert "Base#" in str(extends[0].target)
    assert extends[0].confidence == "high"


def test_extends_edge_for_imported_base() -> None:
    r = _index(
        """
        from abc import ABC

        class Foo(ABC): pass
        """
    )
    extends = [e for e in r.edges if e.kind == "extends"]
    assert len(extends) == 1
    target = str(extends[0].target)
    assert "scip-python" in target
    assert "abc" in target


# ---------------------------------------------------------------------------
# Diagnostics & boundary cases
# ---------------------------------------------------------------------------


def test_syntax_error_isolated_as_diagnostic() -> None:
    r = _index("def broken(:\n    pass\n")
    assert r.symbols == []
    assert r.edges == []
    assert len(r.diagnostics) == 1
    d = r.diagnostics[0]
    assert d.severity == "error"
    assert d.code == "PY001"
    assert "syntax" in d.message.lower()


def test_invalid_utf8_isolated_as_diagnostic() -> None:
    ix = PythonIndexer()
    r = ix.index_file(
        Path("bad.py"),
        b"\xff\xfe garbage \xc3(",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.py"),
            language="python",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "PY002"


def test_empty_file_produces_nothing() -> None:
    r = _index("")
    assert r.symbols == []
    assert r.edges == []
    assert r.diagnostics == []


def test_comments_only_file_produces_nothing() -> None:
    r = _index("# just a comment\n# and another\n")
    assert r.symbols == []


# ---------------------------------------------------------------------------
# SymbolID structure / path encoding
# ---------------------------------------------------------------------------


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("def f(): pass\n", path="pkg/sub/m.py")
    sid = str(r.symbols[0].id)
    assert sid == "scip-python . . . pkg/sub/m.py/f()."


def test_indexer_metadata() -> None:
    ix = PythonIndexer()
    assert ix.name == "python"
    assert ix.languages == ["python"]
    assert "*.py" in ix.file_patterns
    assert "*.pyi" in ix.file_patterns
    assert ix.supports(Path("a.py"))
    assert ix.supports(Path("a.pyi"))
    assert not ix.supports(Path("a.txt"))


# ---------------------------------------------------------------------------
# Range / location
# ---------------------------------------------------------------------------


def test_range_reflects_definition_span() -> None:
    r = _index(
        """
        def f():
            return 1
        """
    )
    rng = r.symbols[0].range
    assert rng.start_line == 1
    assert rng.end_line >= rng.start_line


def test_scheme_is_consistent() -> None:
    r = _index("def f(): pass\nclass C: pass\nX = 1\n")
    for sym in r.symbols:
        assert str(sym.id).startswith(f"{SCHEME} ")


# ---------------------------------------------------------------------------
# HTTP route recognition (decorator-driven)
# ---------------------------------------------------------------------------


def _function_sym(result: IndexResult, name: str):  # type: ignore[no-untyped-def]
    for s in result.symbols:
        if str(s.id).endswith(f"/{name}()."):
            return s
    raise AssertionError(f"no symbol named {name!r} in {[str(s.id) for s in result.symbols]}")


def test_http_route_fastapi_style_get() -> None:
    r = _index(
        """
        @app.get("/api/users")
        def list_users():
            ...
        """
    )
    sym = _function_sym(r, "list_users")
    assert sym.extra["http_route"] == {"method": "GET", "path": "/api/users"}


def test_http_route_fastapi_post() -> None:
    r = _index(
        """
        @router.post("/api/user")
        def create():
            ...
        """
    )
    sym = _function_sym(r, "create")
    assert sym.extra["http_route"]["method"] == "POST"
    assert sym.extra["http_route"]["path"] == "/api/user"


def test_http_route_flask_style_default_get() -> None:
    r = _index(
        """
        @app.route("/api/x")
        def f():
            ...
        """
    )
    sym = _function_sym(r, "f")
    assert sym.extra["http_route"] == {"method": "GET", "path": "/api/x"}


def test_http_route_flask_methods_list() -> None:
    r = _index(
        """
        @app.route("/api/x", methods=["POST", "PUT"])
        def f():
            ...
        """
    )
    sym = _function_sym(r, "f")
    assert sym.extra["http_route"]["method"] == "POST"


def test_http_route_bare_route_decorator() -> None:
    r = _index(
        """
        @route("/x", method="DELETE")
        def f():
            ...
        """
    )
    sym = _function_sym(r, "f")
    assert sym.extra["http_route"]["method"] == "DELETE"


def test_http_route_async_endpoint() -> None:
    r = _index(
        """
        @app.get("/api/x")
        async def f():
            ...
        """
    )
    sym = _function_sym(r, "f")
    assert sym.extra["http_route"]["path"] == "/api/x"
    assert sym.extra["async"] is True


def test_http_route_ignored_when_path_is_dynamic() -> None:
    r = _index(
        """
        PATH = "/api/x"
        @app.get(PATH)
        def f():
            ...
        """
    )
    sym = _function_sym(r, "f")
    assert "http_route" not in sym.extra


def test_http_route_ignored_when_no_decorators() -> None:
    r = _index("def f(): ...\n")
    sym = _function_sym(r, "f")
    assert "http_route" not in sym.extra


def test_non_route_decorator_ignored() -> None:
    r = _index(
        """
        @staticmethod
        @cache
        def f(): ...
        """
    )
    sym = _function_sym(r, "f")
    assert "http_route" not in sym.extra


# ---------------------------------------------------------------------------
# HTTP client call recognition (function-body driven)
# ---------------------------------------------------------------------------


def test_http_client_requests_get() -> None:
    r = _index(
        """
        def fetch():
            return requests.get("/api/users")
        """
    )
    sym = _function_sym(r, "fetch")
    calls = sym.extra["http_calls"]
    assert calls == [
        {"method": "GET", "url": "/api/users", "confidence": "high"},
    ]


def test_http_client_httpx_post_full_url() -> None:
    r = _index(
        """
        def post_user():
            httpx.post("https://api.example.com/user")
        """
    )
    sym = _function_sym(r, "post_user")
    assert sym.extra["http_calls"][0]["method"] == "POST"
    assert sym.extra["http_calls"][0]["url"] == "https://api.example.com/user"


def test_http_client_unknown_receiver_medium_confidence() -> None:
    r = _index(
        """
        def fetch():
            self.client.get("/api/x")
        """
    )
    sym = _function_sym(r, "fetch")
    assert sym.extra["http_calls"][0]["confidence"] == "medium"


def test_http_client_dict_get_is_ignored() -> None:
    """``dict.get('key')`` shares the ``.get(str)`` shape but is not HTTP."""
    r = _index(
        """
        def f(d):
            d.get("name")
            d.get("user_id")
        """
    )
    sym = _function_sym(r, "f")
    assert "http_calls" not in sym.extra


def test_http_client_multiple_calls_collected() -> None:
    r = _index(
        """
        def workflow():
            requests.get("/api/a")
            requests.post("/api/b")
        """
    )
    sym = _function_sym(r, "workflow")
    methods = [c["method"] for c in sym.extra["http_calls"]]
    assert methods == ["GET", "POST"]


def test_http_client_in_nested_block() -> None:
    r = _index(
        """
        def f(x):
            if x:
                requests.get("/api/ok")
        """
    )
    sym = _function_sym(r, "f")
    assert sym.extra["http_calls"][0]["url"] == "/api/ok"


def test_http_client_dynamic_url_ignored() -> None:
    r = _index(
        """
        def f(url):
            requests.get(url)
        """
    )
    sym = _function_sym(r, "f")
    assert "http_calls" not in sym.extra


def test_http_client_relative_path_required() -> None:
    """Paths not starting with `/` or `http(s)://` are ignored."""
    r = _index(
        """
        def f():
            self.session.get("relative/path")
        """
    )
    sym = _function_sym(r, "f")
    assert "http_calls" not in sym.extra


# ---------------------------------------------------------------------------
# Golden directory fixture runner
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "indexers" / "python"


def _scenarios() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return [p for p in sorted(FIXTURES_DIR.iterdir()) if (p / "input").is_dir()]


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda p: p.name)
def test_python_golden(scenario: Path) -> None:
    """For each ``scenario`` under ``tests/fixtures/indexers/python``, index
    every ``.py`` file under ``input/`` and compare the union of all symbol
    IDs (sorted) to ``expected/symbol_ids.txt`` line by line.
    """
    input_dir = scenario / "input"
    expected_file = scenario / "expected" / "symbol_ids.txt"
    if not expected_file.exists():
        pytest.skip(f"no expected/symbol_ids.txt in {scenario.name}")
    ix = PythonIndexer()
    all_ids: set[str] = set()
    for src in sorted(input_dir.rglob("*.py")):
        rel = PurePosixPath(src.relative_to(input_dir).as_posix())
        result = ix.index_file(
            src,
            src.read_bytes(),
            IndexContext(
                project_root=input_dir,
                relative_path=rel,
                language="python",
            ),
        )
        all_ids.update(str(s.id) for s in result.symbols)
    expected = [line.strip() for line in expected_file.read_text().splitlines() if line.strip()]
    assert sorted(all_ids) == sorted(expected)
