"""Unit tests for ``codemap.core.bridge.http_route.HttpRouteBridge``."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from codemap.core.bridge.http_route import SCHEME, HttpRouteBridge
from codemap.core.models import BridgeResult, Range, Symbol
from codemap.core.symbol import SymbolID

# ---------------------------------------------------------------------------
# Stub read-only store
# ---------------------------------------------------------------------------


class _StubStore:
    """Minimal ``ReadOnlyStore`` impl: only ``iter_symbols`` is exercised."""

    def __init__(self, symbols: list[Symbol]) -> None:
        self._symbols = symbols

    def iter_symbols(self):  # type: ignore[no-untyped-def]
        return iter(self._symbols)

    def get(self, sid):  # pragma: no cover
        return None

    def iter_edges(self):  # pragma: no cover
        return iter([])

    def callers(self, sid, *, depth=1):  # pragma: no cover
        return []

    def callees(self, sid, *, depth=1):  # pragma: no cover
        return []

    def search(self, query, *, limit=10):  # pragma: no cover
        return []

    def manifest(self):  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sid(s: str) -> SymbolID:
    return SymbolID.parse(s)


def _server(
    *,
    name: str,
    method: str,
    path: str,
    context: str | None = None,
    file: str = "src/server.py",
) -> Symbol:
    extra: dict[str, Any] = {"http_route": {"method": method, "path": path}}
    if context is not None:
        extra["http_route"]["context_path"] = context
    return Symbol(
        id=_sid(f"scip-python . . . src/server.py/{name}()."),
        kind="route",
        language="python",
        file=PurePosixPath(file),
        range=Range(start_line=1, end_line=5),
        extra=extra,
    )


def _client(
    *,
    name: str,
    calls: list[dict[str, Any]],
    file: str = "src/client.ts",
    language: str = "typescript",
) -> Symbol:
    sid_str = (
        f"scip-typescript . . . src/client.ts/{name}()."
        if language == "typescript"
        else f"scip-python . . . src/client.py/{name}()."
    )
    return Symbol(
        id=_sid(sid_str),
        kind="function",
        language=language,
        file=PurePosixPath(file),
        range=Range(start_line=1, end_line=5),
        extra={"http_calls": calls},
    )


def _run(symbols: list[Symbol]) -> BridgeResult:
    return HttpRouteBridge().resolve(_StubStore(symbols))


# ---------------------------------------------------------------------------
# Empty / trivial cases
# ---------------------------------------------------------------------------


def test_empty_store_returns_empty_result() -> None:
    r = _run([])
    assert r.routes == []
    assert r.aliases == []
    assert r.edges == []
    assert r.diagnostics == []


def test_symbol_without_metadata_is_ignored() -> None:
    sym = Symbol(
        id=_sid("scip-python . . . src/m.py/f()."),
        kind="function",
        language="python",
        file=PurePosixPath("src/m.py"),
        range=Range(start_line=1, end_line=1),
    )
    r = _run([sym])
    assert r.routes == []
    assert r.aliases == []
    assert r.edges == []


# ---------------------------------------------------------------------------
# Server-side: route, alias, routes_to edge minting
# ---------------------------------------------------------------------------


def test_single_server_route_produces_outputs() -> None:
    server = _server(name="list_users", method="GET", path="/api/user/list")
    r = _run([server])
    assert len(r.routes) == 1
    route = r.routes[0]
    assert route.method == "GET"
    assert route.path == "/api/user/list"
    assert str(route.symbol_id).startswith(f"{SCHEME} ")

    assert len(r.aliases) == 1
    assert r.aliases[0].targets == [server.id]

    assert len(r.edges) == 1
    assert r.edges[0].kind == "routes_to"
    assert r.edges[0].source == server.id
    assert r.edges[0].target == route.symbol_id


def test_method_is_normalised_to_uppercase() -> None:
    server = _server(name="x", method="get", path="/x")
    r = _run([server])
    assert r.routes[0].method == "GET"


def test_context_path_is_joined() -> None:
    server = _server(name="x", method="GET", path="user/list", context="api/v1")
    r = _run([server])
    assert r.routes[0].path == "/api/v1/user/list"


def test_context_path_handles_trailing_slashes() -> None:
    server = _server(name="x", method="GET", path="/list/", context="/api/v1/")
    r = _run([server])
    assert r.routes[0].path == "/api/v1/list"


def test_root_path_only() -> None:
    server = _server(name="root", method="GET", path="/")
    r = _run([server])
    assert r.routes[0].path == "/"


def test_duplicate_server_routes_emit_warning() -> None:
    a = _server(name="handler_a", method="GET", path="/users")
    b = _server(name="handler_b", method="GET", path="/users")
    r = _run([a, b])
    assert len(r.routes) == 1
    # Single alias collects both handlers
    assert sorted(str(t) for t in r.aliases[0].targets) == sorted([str(a.id), str(b.id)])
    # Both handlers get routes_to edges
    assert len([e for e in r.edges if e.kind == "routes_to"]) == 2
    # ROUTE001 warning raised
    codes = {d.code for d in r.diagnostics}
    assert "ROUTE001" in codes


# ---------------------------------------------------------------------------
# Client-side: call matching + edge generation
# ---------------------------------------------------------------------------


def test_client_call_to_matching_static_route() -> None:
    server = _server(name="srv", method="GET", path="/api/users")
    client = _client(
        name="fetch_users",
        calls=[{"method": "GET", "url": "/api/users", "confidence": "high"}],
    )
    r = _run([server, client])
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 1
    assert call_edges[0].source == client.id
    assert call_edges[0].confidence == "high"


def test_client_call_with_path_variable_match() -> None:
    server = _server(name="srv", method="GET", path="/api/user/{id}")
    client = _client(
        name="fetch_user",
        calls=[{"method": "GET", "url": "/api/user/42"}],
    )
    r = _run([server, client])
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 1
    assert call_edges[0].confidence == "medium"  # default


def test_client_call_query_string_is_stripped() -> None:
    server = _server(name="srv", method="GET", path="/api/search")
    client = _client(
        name="search",
        calls=[{"method": "GET", "url": "/api/search?q=foo&limit=10"}],
    )
    r = _run([server, client])
    assert len([e for e in r.edges if e.kind == "calls"]) == 1


def test_client_call_to_wrong_method_does_not_match() -> None:
    server = _server(name="srv", method="GET", path="/api/x")
    client = _client(
        name="post_x",
        calls=[{"method": "POST", "url": "/api/x", "confidence": "high"}],
    )
    r = _run([server, client])
    assert [e for e in r.edges if e.kind == "calls"] == []
    assert any(d.code == "ROUTE002" for d in r.diagnostics)


def test_client_call_with_mismatched_segment_count_does_not_match() -> None:
    server = _server(name="srv", method="GET", path="/api/user")
    client = _client(
        name="too_long",
        calls=[{"method": "GET", "url": "/api/user/42", "confidence": "high"}],
    )
    r = _run([server, client])
    assert [e for e in r.edges if e.kind == "calls"] == []


def test_unmatched_low_confidence_call_emits_no_warning() -> None:
    client = _client(
        name="dynamic_url",
        calls=[{"method": "GET", "url": "/dynamic", "confidence": "low"}],
    )
    r = _run([client])
    assert [d for d in r.diagnostics if d.code == "ROUTE002"] == []


def test_unmatched_high_confidence_call_emits_warning() -> None:
    client = _client(
        name="static_url",
        calls=[{"method": "GET", "url": "/static", "confidence": "high"}],
    )
    r = _run([client])
    assert any(d.code == "ROUTE002" for d in r.diagnostics)


# ---------------------------------------------------------------------------
# Aggregation / cross-language scenarios
# ---------------------------------------------------------------------------


def test_multiple_clients_share_one_route_intermediate() -> None:
    server = _server(name="srv", method="GET", path="/api/x")
    c1 = _client(
        name="caller1",
        calls=[{"method": "GET", "url": "/api/x"}],
    )
    c2 = _client(
        name="caller2",
        calls=[{"method": "GET", "url": "/api/x"}],
        language="python",
    )
    r = _run([server, c1, c2])
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 2
    # All call edges point at the SAME route intermediate
    assert {str(e.target) for e in call_edges} == {str(r.routes[0].symbol_id)}


def test_client_with_multiple_calls_creates_multiple_edges() -> None:
    s1 = _server(name="a", method="GET", path="/a")
    s2 = _server(name="b", method="POST", path="/b")
    client = _client(
        name="multi",
        calls=[
            {"method": "GET", "url": "/a"},
            {"method": "POST", "url": "/b"},
        ],
    )
    r = _run([s1, s2, client])
    call_edges = [e for e in r.edges if e.kind == "calls"]
    assert len(call_edges) == 2


# ---------------------------------------------------------------------------
# Defensive: malformed metadata
# ---------------------------------------------------------------------------


def test_malformed_server_metadata_is_ignored() -> None:
    bad = Symbol(
        id=_sid("scip-python . . . src/m.py/f()."),
        kind="function",
        language="python",
        file=PurePosixPath("src/m.py"),
        range=Range(start_line=1, end_line=1),
        extra={
            "http_route": "not a dict",  # wrong type
        },
    )
    bad2 = Symbol(
        id=_sid("scip-python . . . src/m.py/g()."),
        kind="function",
        language="python",
        file=PurePosixPath("src/m.py"),
        range=Range(start_line=1, end_line=1),
        extra={
            "http_route": {"method": "GET"},  # missing path
        },
    )
    r = _run([bad, bad2])
    assert r.routes == []


def test_malformed_client_metadata_is_skipped() -> None:
    client = Symbol(
        id=_sid("scip-python . . . src/c.py/f()."),
        kind="function",
        language="python",
        file=PurePosixPath("src/c.py"),
        range=Range(start_line=1, end_line=1),
        extra={
            "http_calls": [
                "not a dict",
                {"method": "GET"},  # missing url
                {"url": "/a"},  # missing method
                {"method": "", "url": "/a"},  # empty method
                {"method": "GET", "url": "/valid", "confidence": "weird"},
            ],
        },
    )
    server = _server(name="x", method="GET", path="/valid")
    r = _run([client, server])
    call_edges = [e for e in r.edges if e.kind == "calls"]
    # Only the one valid call survives; weird confidence defaults to medium
    assert len(call_edges) == 1
    assert call_edges[0].confidence == "medium"


# ---------------------------------------------------------------------------
# Bridge metadata
# ---------------------------------------------------------------------------


def test_bridge_metadata() -> None:
    b = HttpRouteBridge()
    assert b.name == "http_route"
    assert b.version == "0.1.0"
    assert b.requires == []


# ---------------------------------------------------------------------------
# Route symbol_id is round-trippable
# ---------------------------------------------------------------------------


def test_route_symbol_id_round_trips() -> None:
    server = _server(name="srv", method="GET", path="/api/user/{id}")
    r = _run([server])
    sid_str = str(r.routes[0].symbol_id)
    parsed = SymbolID.parse(sid_str)
    assert parsed.to_string() == sid_str
