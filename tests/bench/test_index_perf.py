"""Indexing throughput benchmark.

Run with::

    pytest tests/bench --benchmark-only -m bench

The default ``pytest`` run skips these (the ``bench`` marker is opt-in).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app

pytestmark = pytest.mark.bench


def _index_run(project: Path) -> None:
    codemap_dir = project / ".codemap"
    if codemap_dir.exists():
        shutil.rmtree(codemap_dir)
    runner = CliRunner()
    result = runner.invoke(app, ["index", str(project), "--no-progress"])
    if result.exit_code != 0:  # pragma: no cover
        raise AssertionError(result.stdout)


def test_bench_full_index_codemap_repo(benchmark, codemap_repo_clone: Path) -> None:  # type: ignore[no-untyped-def]
    """Full index of the CodeMap repo's own source tree.

    Target (design §21): under 60s per 100 KLoC. The CodeMap source is
    roughly 5 KLoC; the absolute budget is therefore ~3 s — we expect
    *well* under one second on modern hardware.
    """
    benchmark.pedantic(
        _index_run,
        args=(codemap_repo_clone,),
        rounds=5,
        iterations=1,
    )
