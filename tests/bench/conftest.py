"""Shared fixtures for the benchmark suite.

Benchmarks are gated behind ``@pytest.mark.bench`` and skipped by default —
the pytest config in ``pyproject.toml`` only collects them when invoked
with ``--benchmark-only`` (or explicitly ``-m bench``). This keeps the
default ``pytest`` invocation fast.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def codemap_repo_clone(tmp_path: Path) -> Path:
    """Copy the entire CodeMap ``src/`` tree into ``tmp_path/subject``.

    Used as the realistic "small but real" subject project: it's the only
    repo guaranteed to be present, it has a non-trivial call graph, and
    measurements stay deterministic.
    """
    repo_root = Path(__file__).resolve().parents[2]
    dest = tmp_path / "subject"
    shutil.copytree(repo_root / "src", dest / "src")
    return dest


@pytest.fixture
def codemap_repo_indexed(codemap_repo_clone: Path) -> Path:
    """Provide the repo clone with a built ``.codemap/`` already in place."""
    from typer.testing import CliRunner

    from codemap.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["index", str(codemap_repo_clone)])
    assert result.exit_code == 0, result.stdout
    return codemap_repo_clone
