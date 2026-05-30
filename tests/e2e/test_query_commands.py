"""End-to-end CLI tests for the query commands: search, get, callers,
callees, trace, routes.

Each test builds a small project on disk, runs ``codemap index`` (so the
Python indexer populates ``.codemap/``), and then drives the relevant
query command through Typer's CliRunner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app
from codemap.diagnostics.exit_codes import ExitCode

runner = CliRunner()


@pytest.fixture
def py_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.py").write_text(
        '"""Sample project."""\n'
        "\n"
        "def helper(x):\n"
        "    return x + 1\n"
        "\n"
        "def caller():\n"
        "    return helper(0)\n"
        "\n"
        "class Greeter:\n"
        "    def hello(self):\n"
        "        return helper(0)\n"
    )
    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0, result.stdout
    return proj


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_finds_known_symbol(py_project: Path) -> None:
    result = runner.invoke(app, ["search", "helper", "--project", str(py_project)])
    assert result.exit_code == 0
    assert "helper" in result.stdout


def test_search_json_envelope(py_project: Path) -> None:
    result = runner.invoke(app, ["--json", "search", "helper", "--project", str(py_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "search"
    assert payload["schema_version"] == "1.0.0"
    assert payload["result"]["query"] == "helper"
    assert len(payload["result"]["results"]) >= 1


def test_search_empty_matches(py_project: Path) -> None:
    result = runner.invoke(
        app, ["search", "definitely_not_a_symbol_xyz", "--project", str(py_project)]
    )
    assert result.exit_code == 0
    assert "No matches" in result.stdout


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_known_symbol(py_project: Path) -> None:
    sid = "scip-python . . . main.py/helper()."
    result = runner.invoke(app, ["get", sid, "--project", str(py_project)])
    assert result.exit_code == 0
    assert "main.py:3" in result.stdout
    assert "def helper" in result.stdout


def test_get_unknown_symbol_exits_nonzero(py_project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "get",
            "scip-python . . . main.py/nonexistent().",
            "--project",
            str(py_project),
        ],
    )
    assert result.exit_code != 0


def test_get_invalid_symbol_id(py_project: Path) -> None:
    result = runner.invoke(app, ["get", "not a symbol", "--project", str(py_project)])
    assert result.exit_code == int(ExitCode.USAGE_ERROR)


def test_get_json_envelope(py_project: Path) -> None:
    sid = "scip-python . . . main.py/helper()."
    result = runner.invoke(app, ["--json", "get", sid, "--project", str(py_project)])
    payload = json.loads(result.stdout)
    assert payload["result"]["found"] is True
    assert payload["result"]["symbol"]["kind"] == "function"
    assert "def helper" in payload["result"]["snippet"]


# ---------------------------------------------------------------------------
# callers / callees
# ---------------------------------------------------------------------------


def test_callers_of_helper(py_project: Path) -> None:
    sid = "scip-python . . . main.py/helper()."
    result = runner.invoke(app, ["callers", sid, "--project", str(py_project)])
    assert result.exit_code == 0
    # Two same-file callers: caller() and Greeter.hello()
    assert "Callers" in result.stdout


def test_callers_json_results(py_project: Path) -> None:
    sid = "scip-python . . . main.py/helper()."
    result = runner.invoke(app, ["--json", "callers", sid, "--project", str(py_project)])
    payload = json.loads(result.stdout)
    callers = payload["result"]["results"]
    assert len(callers) >= 2
    sources = [c["symbol"] for c in callers]
    assert any("caller" in s for s in sources)


def test_callees_of_caller(py_project: Path) -> None:
    sid = "scip-python . . . main.py/caller()."
    result = runner.invoke(app, ["--json", "callees", sid, "--project", str(py_project)])
    payload = json.loads(result.stdout)
    targets = [c["symbol"] for c in payload["result"]["results"]]
    assert any("helper" in t for t in targets)


def test_callers_with_no_match_friendly_message(py_project: Path) -> None:
    sid = "scip-python . . . main.py/Greeter#"
    result = runner.invoke(app, ["callers", sid, "--project", str(py_project)])
    assert result.exit_code == 0
    assert "No callers" in result.stdout


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


def test_trace_from_caller_finds_helper(py_project: Path) -> None:
    sid = "scip-python . . . main.py/caller()."
    result = runner.invoke(
        app, ["--json", "trace", "--from", sid, "-d", "2", "--project", str(py_project)]
    )
    payload = json.loads(result.stdout)
    # Walk should include at least helper as a child
    children_ids = [c["id"] for c in payload["result"]["children"]]
    assert any("helper" in i for i in children_ids)


def test_trace_text_output_has_root(py_project: Path) -> None:
    sid = "scip-python . . . main.py/caller()."
    result = runner.invoke(app, ["trace", "--from", sid, "-d", "2", "--project", str(py_project)])
    assert result.exit_code == 0
    assert "main.py" in result.stdout


def test_trace_with_to_finds_path(py_project: Path) -> None:
    from_sid = "scip-python . . . main.py/caller()."
    to_sid = "scip-python . . . main.py/helper()."
    result = runner.invoke(
        app,
        [
            "--json",
            "trace",
            "--from",
            from_sid,
            "--to",
            to_sid,
            "-d",
            "3",
            "--project",
            str(py_project),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["found"] is True
    assert len(payload["result"]["path"]) == 2  # caller -> helper


def test_trace_no_path_exit_nonzero(py_project: Path) -> None:
    from_sid = "scip-python . . . main.py/caller()."
    to_sid = "scip-python . . . main.py/Greeter#hello()."
    result = runner.invoke(
        app,
        [
            "trace",
            "--from",
            from_sid,
            "--to",
            to_sid,
            "-d",
            "2",
            "--project",
            str(py_project),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


def test_routes_with_no_data_friendly_message(py_project: Path) -> None:
    result = runner.invoke(app, ["routes", "--project", str(py_project)])
    assert result.exit_code == 0
    assert "No routes" in result.stdout


def test_routes_after_seeding_http_metadata(tmp_path: Path) -> None:
    """Seed the JsonStore directly with http_route metadata, run the Bridge
    via a fresh index, then verify ``codemap routes`` surfaces them.
    """
    from datetime import UTC, datetime
    from pathlib import PurePosixPath

    from codemap.core.bridge.http_route import HttpRouteBridge
    from codemap.core.models import Manifest, Range, Symbol
    from codemap.core.symbol import SymbolID
    from codemap.io.json_store import JsonStore

    proj = tmp_path / "py_routes"
    proj.mkdir()
    cmdir = proj / ".codemap"

    server = Symbol(
        id=SymbolID.parse("scip-python . . . server.py/list_users()."),
        kind="function",
        language="python",
        file=PurePosixPath("server.py"),
        range=Range(start_line=1, end_line=2),
        extra={"http_route": {"method": "GET", "path": "/api/users"}},
    )
    with JsonStore.open(cmdir) as store:
        store.upsert_symbols([server])
        result = HttpRouteBridge().resolve(store)
        store.upsert_routes(result.routes)
        store.upsert_aliases(result.aliases)
        store.upsert_edges(result.edges)
        store.set_manifest(
            Manifest(
                codemap_version="0.1.0",
                project_root=str(proj.resolve()),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        store.commit()

    res = runner.invoke(app, ["--json", "routes", "--project", str(proj)])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    routes = payload["result"]["results"]
    assert len(routes) == 1
    assert routes[0]["method"] == "GET"
    assert routes[0]["path"] == "/api/users"
    assert routes[0]["handlers"][0]["file"] == "server.py"


def test_routes_method_filter(tmp_path: Path) -> None:
    from datetime import UTC, datetime
    from pathlib import PurePosixPath

    from codemap.core.bridge.http_route import HttpRouteBridge
    from codemap.core.models import Manifest, Range, Symbol
    from codemap.core.symbol import SymbolID
    from codemap.io.json_store import JsonStore

    proj = tmp_path / "py_routes2"
    proj.mkdir()
    cmdir = proj / ".codemap"

    def _server(name: str, method: str, path: str) -> Symbol:
        return Symbol(
            id=SymbolID.parse(f"scip-python . . . server.py/{name}()."),
            kind="function",
            language="python",
            file=PurePosixPath("server.py"),
            range=Range(start_line=1, end_line=2),
            extra={"http_route": {"method": method, "path": path}},
        )

    with JsonStore.open(cmdir) as store:
        store.upsert_symbols([_server("g", "GET", "/a"), _server("p", "POST", "/b")])
        r = HttpRouteBridge().resolve(store)
        store.upsert_routes(r.routes)
        store.upsert_aliases(r.aliases)
        store.upsert_edges(r.edges)
        store.set_manifest(
            Manifest(
                codemap_version="0.1.0",
                project_root=str(proj.resolve()),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        store.commit()

    res = runner.invoke(app, ["--json", "routes", "--method", "GET", "--project", str(proj)])
    payload = json.loads(res.stdout)
    routes = payload["result"]["results"]
    assert len(routes) == 1
    assert routes[0]["method"] == "GET"


# ---------------------------------------------------------------------------
# Common error paths
# ---------------------------------------------------------------------------


def test_query_without_index_exits_no_input(tmp_path: Path) -> None:
    result = runner.invoke(app, ["search", "x", "--project", str(tmp_path)])
    assert result.exit_code == int(ExitCode.NO_INPUT)
