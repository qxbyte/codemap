"""Plan 1 Task 4: language-neutral git change-frequency analyzer."""

from __future__ import annotations

import subprocess
from pathlib import Path

from codemap.core.git_hotspots import change_counts


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def test_counts_changes(tmp_path: Path) -> None:
    _run(["git", "init"], tmp_path)
    _run(["git", "config", "user.email", "t@t"], tmp_path)
    _run(["git", "config", "user.name", "t"], tmp_path)
    _run(["git", "config", "commit.gpgsign", "false"], tmp_path)
    f = tmp_path / "a.txt"
    f.write_text("1")
    _run(["git", "add", "."], tmp_path)
    _run(["git", "commit", "-m", "1"], tmp_path)
    f.write_text("2")
    _run(["git", "commit", "-am", "2"], tmp_path)

    counts = change_counts(tmp_path, since_days=90)
    assert counts["a.txt"] == 2


def test_non_git_returns_empty(tmp_path: Path) -> None:
    assert change_counts(tmp_path) == {}
