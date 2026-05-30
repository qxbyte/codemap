"""Integration test: HttpRouteBridge running against a real JsonStore.

Walks the full lifecycle a real ``codemap index`` would: write a handful of
symbols (with ``http_route`` / ``http_calls`` metadata) into a JsonStore,
run the Bridge, commit the result, reopen the store and verify the
``routes.json`` / ``aliases.json`` / ``edges.json`` payloads match what
the unit tests pin down.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from codemap.core.bridge.http_route import HttpRouteBridge
from codemap.core.models import Manifest, Range, Symbol
from codemap.core.symbol import SymbolID
from codemap.io.json_store import JsonStore


def _server_symbol(*, name: str, method: str, path: str) -> Symbol:
    return Symbol(
        id=SymbolID.parse(f"scip-python . . . src/server.py/{name}()."),
        kind="function",
        language="python",
        file=PurePosixPath("src/server.py"),
        range=Range(start_line=1, end_line=5),
        extra={"http_route": {"method": method, "path": path}},
    )


def _client_symbol(*, name: str, calls: list[dict[str, Any]]) -> Symbol:
    return Symbol(
        id=SymbolID.parse(f"scip-typescript . . . src/client.ts/{name}()."),
        kind="function",
        language="typescript",
        file=PurePosixPath("src/client.ts"),
        range=Range(start_line=1, end_line=5),
        extra={"http_calls": calls},
    )


def test_bridge_round_trip_through_json_store(tmp_path: Path) -> None:
    server_list = _server_symbol(name="list_users", method="GET", path="/api/users")
    server_get = _server_symbol(name="get_user", method="GET", path="/api/user/{id}")
    client_list = _client_symbol(
        name="fetchUsers",
        calls=[{"method": "GET", "url": "/api/users", "confidence": "high"}],
    )
    client_get = _client_symbol(
        name="fetchUser",
        calls=[{"method": "GET", "url": "/api/user/42", "confidence": "high"}],
    )

    bridge = HttpRouteBridge()

    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([server_list, server_get, client_list, client_get])
        result = bridge.resolve(store)
        store.upsert_edges(result.edges)
        store.upsert_aliases(result.aliases)
        store.upsert_routes(result.routes)
        store.upsert_diagnostics(result.diagnostics)
        store.set_manifest(
            Manifest(
                codemap_version="0.1.0",
                project_root="/tmp/proj",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        store.commit()

    # Reopen and assert on the persisted shapes.
    with JsonStore.open(tmp_path, mode="r") as store:
        manifest = store.manifest()
    assert manifest.stats.route_count == 2
    assert manifest.stats.alias_count == 2

    routes = json.loads((tmp_path / "routes.json").read_text())
    methods_and_paths = sorted((r["method"], r["path"]) for r in routes)
    assert methods_and_paths == [
        ("GET", "/api/user/{id}"),
        ("GET", "/api/users"),
    ]

    aliases = json.loads((tmp_path / "aliases.json").read_text())
    # Each alias chain has exactly one server-handler target
    for alias in aliases:
        assert len(alias["targets"]) == 1
        assert alias["producer"] == "http_route"

    edges = json.loads((tmp_path / "edges.json").read_text())
    routes_to = [e for e in edges if e["kind"] == "routes_to"]
    calls = [e for e in edges if e["kind"] == "calls"]
    assert len(routes_to) == 2  # 2 server handlers → 2 intermediate edges
    assert len(calls) == 2  # 2 client calls → 2 edges
    # Client edges target the route intermediate, not the server symbol directly
    for e in calls:
        assert e["target"].startswith("scip-route ")
