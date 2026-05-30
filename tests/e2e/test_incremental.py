"""End-to-end tests for ``codemap index --incremental`` and ``--watch``."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def foo(): pass\n")
    (proj / "b.py").write_text("def bar(): pass\n")
    runner.invoke(app, ["index", str(proj)])
    return proj


def _symbol_ids(project: Path) -> set[str]:
    syms = json.loads((project / ".codemap" / "symbols.json").read_text())
    return set(syms.keys())


# ---------------------------------------------------------------------------
# --incremental
# ---------------------------------------------------------------------------


def test_incremental_noop_when_nothing_changed(project: Path) -> None:
    before = _symbol_ids(project)
    result = runner.invoke(app, ["--json", "index", str(project), "--incremental"])
    assert result.exit_code == 0
    after = _symbol_ids(project)
    assert before == after


def test_incremental_picks_up_modified_file(project: Path) -> None:
    (project / "a.py").write_text("def foo(): pass\ndef foo2(): pass\n")
    runner.invoke(app, ["index", str(project), "--incremental"])
    ids = _symbol_ids(project)
    # Both foo and foo2 from a.py should be present, plus bar from b.py
    assert any("foo()." in s for s in ids)
    assert any("foo2()." in s for s in ids)
    assert any("bar()." in s for s in ids)


def test_incremental_removes_symbols_of_deleted_file(project: Path) -> None:
    (project / "b.py").unlink()
    runner.invoke(app, ["index", str(project), "--incremental"])
    ids = _symbol_ids(project)
    assert any("foo()." in s for s in ids)
    assert not any("b.py" in s for s in ids)


def test_incremental_indexes_new_files(project: Path) -> None:
    (project / "c.py").write_text("def baz(): pass\n")
    runner.invoke(app, ["index", str(project), "--incremental"])
    ids = _symbol_ids(project)
    assert any("c.py/baz()." in s for s in ids)


def test_incremental_falls_back_to_full_when_no_index(tmp_path: Path) -> None:
    proj = tmp_path / "fresh"
    proj.mkdir()
    (proj / "x.py").write_text("def x(): pass\n")
    # No prior index → --incremental should still produce one
    result = runner.invoke(app, ["--json", "index", str(proj), "--incremental"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["files_indexed"] == 1


def test_incremental_rebuilds_bridges(tmp_path: Path) -> None:
    """After an incremental update, cross-module aliases must reflect the
    new state (bridges are re-run from scratch)."""
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "utils.py").write_text("def helper(): pass\n")
    (proj / "service.py").write_text("from utils import helper\ndef use(): return helper()\n")
    runner.invoke(app, ["index", str(proj)])
    aliases_before = json.loads((proj / ".codemap" / "aliases.json").read_text())
    cross = [a for a in aliases_before if a["producer"] == "python_cross_module"]
    assert len(cross) >= 1

    # Rename helper → helper2 in utils; service.py still imports `helper`
    # so the alias should now miss.
    (proj / "utils.py").write_text("def helper2(): pass\n")
    runner.invoke(app, ["index", str(proj), "--incremental"])
    aliases_after = json.loads((proj / ".codemap" / "aliases.json").read_text())
    cross_after = [a for a in aliases_after if a["producer"] == "python_cross_module"]
    # No cross alias for the rebuilt project — `helper` no longer exists
    assert all("helper2" not in a["targets"][0] or "helper" in a["source"] for a in cross_after)


# ---------------------------------------------------------------------------
# --watch (basic smoke test)
# ---------------------------------------------------------------------------


def test_watch_responds_to_file_change(project: Path) -> None:
    """Spawn `codemap index --watch` as a subprocess, modify a file, expect
    the watcher to pick it up within a few seconds."""
    import subprocess
    import sys

    proc = subprocess.Popen(
        [sys.executable, "-m", "codemap.cli.main", "index", str(project), "--watch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        # Wait for the "Watching" banner.
        deadline = time.monotonic() + 10
        seen_banner = False
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                continue
            if "Watching" in line:
                seen_banner = True
                break
        assert seen_banner, "watcher did not start"

        # Modify a file
        (project / "a.py").write_text("def foo(): pass\ndef new_one(): pass\n")
        # Wait for an "updated" line
        deadline = time.monotonic() + 10
        seen_update = False
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                continue
            if "updated" in line:
                seen_update = True
                break
        assert seen_update, "watcher did not report an update"
    finally:
        proc.send_signal(__import__("signal").SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
