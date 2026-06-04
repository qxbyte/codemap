"""Unit tests for the JSP indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_jsp import JspIndexer
from codemap_jsp.indexer import SCHEME
from codemap_jsp.sfc import extract

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "src/pages/UserList.jsp") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return JspIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="jsp",
        ),
    )


# ---------------------------------------------------------------------------
# Scanner (no parser dependency)
# ---------------------------------------------------------------------------


def test_extract_page_imports() -> None:
    ext = extract(b'<%@ page contentType="text/html" import="java.util.List, java.util.Map" %>')
    fqcns = [i.fqcn for i in ext.imports]
    assert fqcns == ["java.util.List", "java.util.Map"]


def test_extract_includes() -> None:
    ext = extract(b'<%@ include file="header.jsp" %>')
    assert [i.path for i in ext.includes] == ["header.jsp"]


def test_extract_form_action_and_method() -> None:
    ext = extract(b'<form action="/save" method="POST">')
    assert ext.form_actions[0].method == "POST"
    assert ext.form_actions[0].url == "/save"


def test_extract_form_action_default_method_is_get() -> None:
    ext = extract(b'<form action="/login">')
    assert ext.form_actions[0].method == "GET"


def test_extract_links() -> None:
    ext = extract(b'<a href="/admin">A</a> <a href="#section">B</a>')
    # The anchor `#section` link is intentionally skipped.
    assert [link.url for link in ext.links] == ["/admin"]


def test_extract_scriptlets_vs_declarations() -> None:
    src = b"<%! private int counter = 0; %>\n<% counter++; %>"
    ext = extract(src)
    assert len(ext.declarations) == 1
    assert b"counter = 0" in ext.declarations[0].content
    assert len(ext.scriptlets) == 1
    assert b"counter++" in ext.scriptlets[0].content


# ---------------------------------------------------------------------------
# Indexer metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = JspIndexer()
    assert ix.name == "jsp"
    assert ix.languages == ["jsp"]
    assert set(ix.file_patterns) == {"*.jsp", "*.jspx", "*.tag", "*.tagx"}
    assert ix.supports(Path("a.jsp"))
    assert ix.supports(Path("a.jspx"))
    assert ix.supports(Path("a.tag"))
    assert not ix.supports(Path("a.html"))


# ---------------------------------------------------------------------------
# Indexer: page-level symbol
# ---------------------------------------------------------------------------


def test_page_symbol_is_class_with_full_range() -> None:
    r = _index(
        """
        <%@ page contentType="text/html" %>
        <html>
            <body>Hello</body>
        </html>
        """
    )
    page = next(s for s in r.symbols if s.kind == "class")
    assert "UserList" in str(page.id)
    assert page.range is not None
    assert page.range.start_line == 1


def test_page_symbol_records_imports_in_extra() -> None:
    r = _index('<%@ page import="java.util.List, com.example.Foo" %>')
    page = next(s for s in r.symbols if s.kind == "class")
    fqcns = {i["fqcn"] for i in page.extra["jsp_imports"]}
    assert fqcns == {"java.util.List", "com.example.Foo"}


def test_page_symbol_records_form_action_for_http_route_bridge() -> None:
    r = _index(
        """
        <form action="/api/users" method="POST">
            <input name="email" />
            <button type="submit">Go</button>
        </form>
        """
    )
    page = next(s for s in r.symbols if s.kind == "class")
    calls = page.extra["http_client_calls"]
    assert any(c["method"] == "POST" and c["url"] == "/api/users" for c in calls)


def test_page_symbol_records_a_href_link() -> None:
    r = _index('<a href="/admin/panel">Admin</a>')
    page = next(s for s in r.symbols if s.kind == "class")
    calls = page.extra["http_client_calls"]
    assert any(c["method"] == "GET" and c["url"] == "/admin/panel" for c in calls)


# ---------------------------------------------------------------------------
# Declaration block (Java <%! ... %>)
# ---------------------------------------------------------------------------


def test_declaration_block_method_indexed() -> None:
    r = _index(
        """
        <%! public String greet(String name) { return "Hi " + name; } %>
        """
    )
    method = next(s for s in r.symbols if s.kind == "method")
    assert "greet" in str(method.id)
    assert method.signature is not None
    assert "greet" in method.signature


def test_declaration_block_field_indexed_as_variable() -> None:
    r = _index("<%! private int counter = 0; %>")
    var = next(s for s in r.symbols if s.kind == "variable")
    assert "counter" in str(var.id)


def test_declaration_block_nested_class_indexed() -> None:
    r = _index(
        """
        <%!
            private class Helper {
                public int compute() { return 42; }
            }
        %>
        """
    )
    kinds = sorted(s.kind for s in r.symbols)
    assert "class" in kinds  # page + nested
    assert "method" in kinds  # compute()


# ---------------------------------------------------------------------------
# Symbol line translation
# ---------------------------------------------------------------------------


def test_declaration_symbol_line_accounts_for_html_above() -> None:
    r = _index(
        """
        <%@ page contentType="text/html" %>
        <html>
            <head><title>x</title></head>
            <body>
                <h1>Header</h1>
        <%! public String tag() { return "x"; } %>
            </body>
        </html>
        """
    )
    method = next(s for s in r.symbols if s.kind == "method")
    assert method.range is not None
    # The <%! ... %> is on line 7 of the dedented source — the symbol
    # must reflect that, not line 1.
    assert method.range.start_line >= 6


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_invalid_utf8_yields_error_diagnostic() -> None:
    ix = JspIndexer()
    r = ix.index_file(
        Path("bad.jsp"),
        b"\xff\xfe garbage",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.jsp"),
            language="jsp",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "JSP002"


def test_scheme_constant() -> None:
    assert SCHEME == "scip-jsp"
