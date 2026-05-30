"""End-to-end CLI tests using Typer's CliRunner.

These exercise the same code paths a real shell invocation goes through
(arg parsing, exit codes, output rendering) without spawning subprocesses.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app
from codemap.diagnostics.exit_codes import ExitCode

runner = CliRunner()


@pytest.fixture
def smoke_project(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[1] / "fixtures" / "smoke"
    if not src.exists():
        pytest.skip("smoke fixture not present")
    dest = tmp_path / "proj"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".codemap"))
    return dest


# ---------------------------------------------------------------------------
# Top-level flags
# ---------------------------------------------------------------------------


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    from codemap import __version__

    assert __version__ in result.stdout


def test_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "index" in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # no_args_is_help=True → typer exits with Click's default for "show help"
    # which is 0 in modern Click, 2 in older.
    assert "doctor" in result.stdout
    assert result.exit_code in (0, 2)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def test_doctor_on_empty_dir_succeeds(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", str(tmp_path)])
    assert result.exit_code == 0
    assert "Registered indexers" in result.stdout
    assert "_example_lang" in result.stdout
    assert "No `.codemap/`" in result.stdout


def test_doctor_json_output_envelope(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--json", "doctor", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "doctor"
    assert payload["schema_version"] == "1.0.0"
    assert payload["result"]["index"]["status"] == "absent"
    names = [ix["name"] for ix in payload["result"]["indexers"]]
    assert "_example_lang" in names


def test_doctor_reports_corrupted_index(tmp_path: Path) -> None:
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "manifest.json").write_text("[]")  # not a JSON object
    result = runner.invoke(app, ["doctor", str(tmp_path)])
    assert result.exit_code == int(ExitCode.DATA_ERROR)
    assert "corrupted" in result.stdout.lower()


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


def test_index_smoke_project(smoke_project: Path) -> None:
    result = runner.invoke(app, ["index", str(smoke_project)])
    assert result.exit_code == 0
    assert "Indexed" in result.stdout
    assert (smoke_project / ".codemap" / "manifest.json").exists()
    assert (smoke_project / ".codemap" / "symbols.json").exists()
    assert (smoke_project / ".codemap" / "edges.json").exists()


def test_index_json_output(smoke_project: Path) -> None:
    result = runner.invoke(app, ["--json", "index", str(smoke_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "index"
    res = payload["result"]
    assert res["files_indexed"] >= 1
    assert res["symbols"] >= 1


def test_index_rebuild_overwrites(smoke_project: Path) -> None:
    # First index
    runner.invoke(app, ["index", str(smoke_project)])
    sym_path = smoke_project / ".codemap" / "symbols.json"
    first = sym_path.read_bytes()
    # Mutate the source so a second indexing would change the symbols file
    (smoke_project / "a.example").write_text("def renamed\n")
    result = runner.invoke(app, ["index", "--rebuild", str(smoke_project)])
    assert result.exit_code == 0
    second = sym_path.read_bytes()
    assert first != second


def test_doctor_after_index_status_ok(smoke_project: Path) -> None:
    runner.invoke(app, ["index", str(smoke_project)])
    result = runner.invoke(app, ["--json", "doctor", str(smoke_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["index"]["status"] == "ok"
    assert payload["result"]["index"]["info"]["symbol_count"] >= 1


# ---------------------------------------------------------------------------
# Python indexer end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    proj = tmp_path / "py_proj"
    proj.mkdir()
    (proj / "main.py").write_text(
        "def helper():\n    return 1\n\ndef entry():\n    return helper()\n"
    )
    return proj


def test_index_python_project_via_cli(python_project: Path) -> None:
    result = runner.invoke(app, ["--json", "index", str(python_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    res = payload["result"]
    assert res["files_indexed"] == 1
    assert res["symbols"] >= 2  # helper + entry
    assert res["edges"] >= 1  # entry -> helper


def test_doctor_lists_python_indexer(python_project: Path) -> None:
    result = runner.invoke(app, ["--json", "doctor", str(python_project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = [ix["name"] for ix in payload["result"]["indexers"]]
    assert "python" in names
