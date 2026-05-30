"""End-to-end tests for the error-experience improvements: dry-run,
indexer/bridge exception isolation as diagnostics, and the friendly
CLI exception wrapper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


@pytest.fixture
def py_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f(): pass\n")
    (proj / "b.py").write_text("def g(): pass\n")
    return proj


def test_dry_run_does_not_write_codemap(py_project: Path) -> None:
    result = runner.invoke(app, ["index", str(py_project), "--dry-run"])
    assert result.exit_code == 0
    assert not (py_project / ".codemap").exists()


def test_dry_run_reports_file_counts(py_project: Path) -> None:
    result = runner.invoke(app, ["--json", "index", str(py_project), "--dry-run"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    res = payload["result"]
    assert res["dry_run"] is True
    assert res["files_matched"] == 2
    assert res["per_indexer"]["python"] == 2
    assert "python" in res["indexers_enabled"]


def test_dry_run_text_output(py_project: Path) -> None:
    result = runner.invoke(app, ["index", str(py_project), "--dry-run"])
    assert "Dry-run" in result.stdout
    assert "would index" in result.stdout


# ---------------------------------------------------------------------------
# Indexer crash → Diagnostic
# ---------------------------------------------------------------------------


def test_indexer_crash_becomes_diagnostic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If an indexer raises mid-file, the run completes and the failure
    appears as an ``INDEXER_CRASH`` diagnostic, not a Python traceback."""
    import codemap.indexers.python

    real_index_file = codemap.indexers.python.PythonIndexer.index_file

    def boom(self, path, source, ctx):  # type: ignore[no-untyped-def]
        if "broken.py" in str(path):
            raise RuntimeError("simulated crash")
        return real_index_file(self, path, source, ctx)

    monkeypatch.setattr(codemap.indexers.python.PythonIndexer, "index_file", boom)

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("def ok(): pass\n")
    (proj / "broken.py").write_text("def x(): pass\n")

    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0
    assert "Traceback" not in result.stdout

    diag = runner.invoke(
        app,
        ["--json", "diagnostics", "--code", "INDEXER_CRASH", "--project", str(proj)],
    )
    payload = json.loads(diag.stdout)
    assert payload["result"]["matched"] == 1
    crash = payload["result"]["results"][0]
    assert crash["producer"] == "python"
    assert "broken.py" in crash["file"]
    assert "simulated crash" in crash["message"]


def test_bridge_crash_becomes_diagnostic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If a bridge raises, the index commits anyway and the failure shows
    up as a ``BRIDGE_CRASH`` diagnostic."""
    import codemap.core.bridge.http_route

    def boom(self, store):  # type: ignore[no-untyped-def]
        raise RuntimeError("bridge boom")

    monkeypatch.setattr(codemap.core.bridge.http_route.HttpRouteBridge, "resolve", boom)

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f(): pass\n")
    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0

    diag = runner.invoke(
        app, ["--json", "diagnostics", "--code", "BRIDGE_CRASH", "--project", str(proj)]
    )
    payload = json.loads(diag.stdout)
    assert payload["result"]["matched"] == 1
    assert payload["result"]["results"][0]["producer"] == "http_route"


def test_io_error_becomes_diagnostic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An unreadable source file becomes an ``IO001`` diagnostic, not a
    silent skip."""
    from pathlib import Path as RealPath

    real_read = RealPath.read_bytes

    def fail_one(self):  # type: ignore[no-untyped-def]
        if str(self).endswith("locked.py"):
            raise PermissionError("permission denied")
        return real_read(self)

    monkeypatch.setattr(RealPath, "read_bytes", fail_one)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("def ok(): pass\n")
    (proj / "locked.py").write_text("def locked(): pass\n")
    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0
    diag = runner.invoke(app, ["--json", "diagnostics", "--code", "IO001", "--project", str(proj)])
    payload = json.loads(diag.stdout)
    assert payload["result"]["matched"] == 1
    assert "locked.py" in payload["result"]["results"][0]["file"]
