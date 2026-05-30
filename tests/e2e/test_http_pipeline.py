"""End-to-end: Python indexer + http_route bridge running together.

These tests prove the full pipeline works in one shot:

1. A small Python project ships a FastAPI-style server file and a
   ``httpx``-style client file.
2. ``codemap index`` runs the Python indexer, which sets
   ``Symbol.extra["http_route"]`` and ``Symbol.extra["http_calls"]``
   on the relevant symbols.
3. The ``http_route`` bridge runs automatically (registered through
   entry_points), reads the metadata, mints ``scip-route`` intermediates,
   and persists ``routes.json`` / ``aliases.json`` / ``edges.json``.
4. ``codemap routes`` surfaces the routes via the CLI.
5. ``codemap callers`` against the route intermediate finds the client.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app

runner = CliRunner()


@pytest.fixture
def http_project(tmp_path: Path) -> Path:
    proj = tmp_path / "service"
    proj.mkdir()
    (proj / "server.py").write_text(
        "app = object()  # stand-in for FastAPI()\n"
        "\n"
        "@app.get('/api/users')\n"
        "def list_users():\n"
        "    return []\n"
        "\n"
        "@app.post('/api/user')\n"
        "def create_user():\n"
        "    return {}\n"
        "\n"
        "@app.get('/api/user/{id}')\n"
        "def get_user(id):\n"
        "    return {}\n"
    )
    (proj / "client.py").write_text(
        "import httpx\n"
        "\n"
        "def fetch_users():\n"
        "    return httpx.get('/api/users')\n"
        "\n"
        "def fetch_user(uid):\n"
        "    return httpx.get(f'/api/user/{uid}')  # dynamic — ignored\n"
        "\n"
        "def add_user():\n"
        "    return httpx.post('/api/user')\n"
    )
    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0, result.stdout
    return proj


def test_routes_command_lists_registered_endpoints(http_project: Path) -> None:
    result = runner.invoke(app, ["--json", "routes", "--project", str(http_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    pairs = sorted((r["method"], r["path"]) for r in payload["result"]["results"])
    assert pairs == [
        ("GET", "/api/user/{id}"),
        ("GET", "/api/users"),
        ("POST", "/api/user"),
    ]
    # Each route resolves to exactly one handler from server.py
    for route in payload["result"]["results"]:
        assert len(route["handlers"]) == 1
        assert route["handlers"][0]["file"] == "server.py"


def test_doctor_reports_clean_pipeline(http_project: Path) -> None:
    result = runner.invoke(app, ["--json", "doctor", str(http_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["index"]["status"] == "ok"
    # http_route bridge was registered and ran
    bridge_names = [b["name"] for b in payload["result"]["bridges"]]
    assert "http_route" in bridge_names


def test_callers_of_route_intermediate_finds_client(http_project: Path) -> None:
    """The route intermediate (scip-route ...) should attract `calls` edges
    from any client function that hit the same path.
    """
    # First find the route SymbolID via `routes --json`
    routes_res = runner.invoke(
        app, ["--json", "routes", "--method", "GET", "--project", str(http_project)]
    )
    routes = json.loads(routes_res.stdout)["result"]["results"]
    list_users_route = next(r for r in routes if r["path"] == "/api/users" and r["method"] == "GET")
    callers_res = runner.invoke(
        app,
        [
            "--json",
            "callers",
            list_users_route["route_id"],
            "--project",
            str(http_project),
        ],
    )
    assert callers_res.exit_code == 0
    callers = json.loads(callers_res.stdout)["result"]["results"]
    caller_ids = [c["symbol"] for c in callers]
    # client.py:fetch_users() should be on the caller list
    assert any("client.py" in cid and "fetch_users" in cid for cid in caller_ids)


def test_dynamic_url_does_not_match(http_project: Path) -> None:
    """``fetch_user`` uses an f-string URL → no http_call recorded → no edge."""
    routes_res = runner.invoke(app, ["--json", "routes", "--project", str(http_project)])
    routes = json.loads(routes_res.stdout)["result"]["results"]
    user_id_route = next(r for r in routes if r["path"] == "/api/user/{id}")
    callers_res = runner.invoke(
        app,
        [
            "--json",
            "callers",
            user_id_route["route_id"],
            "--project",
            str(http_project),
        ],
    )
    callers = json.loads(callers_res.stdout)["result"]["results"]
    caller_ids = [c["symbol"] for c in callers]
    # Only the server handler itself (via routes_to edge) should appear,
    # not fetch_user (which had a dynamic URL).
    assert not any("fetch_user" in cid for cid in caller_ids)
