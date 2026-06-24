"""Plan 1 Task 5: orchestrator phases — project indexers, hotspots, emitters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codemap.cli.commands.index import (
    _apply_hotspots,
    _IndexStats,
    _run_emitters,
    _run_project_indexers,
)
from codemap.config import load_config
from codemap.core.models import IndexResult, Range, Symbol
from codemap.core.store import ReadOnlyStore
from codemap.core.symbol import SymbolID
from codemap.emitters.base import EmitContext, EmitResult
from codemap.emitters.registry import EmitterRegistry
from codemap.indexers.project_registry import ProjectIndexerRegistry
from codemap.io.json_store import JsonStore


class _FakeProjectIndexer:
    name = "fake-java"
    version = "0.1.0"

    def index_project(self, ctx: Any) -> IndexResult:
        sid = SymbolID.parse("scip-java . . . src/B.java/B#")
        return IndexResult(
            symbols=[
                Symbol(
                    id=sid,
                    kind="class",
                    language="java",
                    file="src/B.java",
                    range=Range(start_line=1, end_line=1),
                )
            ]
        )


class _FakeCrashIndexer:
    name = "boom"
    version = "0.1.0"

    def index_project(self, ctx: Any) -> IndexResult:
        raise RuntimeError("boom")


def test_project_indexer_phase_writes_symbols(tmp_path: Path) -> None:
    reg = ProjectIndexerRegistry()
    reg.register(_FakeProjectIndexer())
    with JsonStore.open(tmp_path / ".codemap") as store:
        n = _run_project_indexers(tmp_path, store, registry=reg)
        store.commit()
        sid = SymbolID.parse("scip-java . . . src/B.java/B#")
        assert store.get(sid) is not None
    assert n == 1


def test_project_indexer_crash_records_diagnostic(tmp_path: Path) -> None:
    reg = ProjectIndexerRegistry()
    reg.register(_FakeCrashIndexer())
    with JsonStore.open(tmp_path / ".codemap") as store:
        n = _run_project_indexers(tmp_path, store, registry=reg)
        store.commit()
        diags = list(store.iter_diagnostics())
    assert n == 0
    assert any(d.code == "PROJECT_INDEXER_CRASH" for d in diags)


def test_apply_hotspots_sets_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = SymbolID.parse("scip-java . . . src/B.java/B#")
    with JsonStore.open(tmp_path / ".codemap") as store:
        store.upsert_symbols(
            [
                Symbol(
                    id=sid,
                    kind="class",
                    language="java",
                    file="src/B.java",
                    range=Range(start_line=1, end_line=1),
                )
            ]
        )
        monkeypatch.setattr(
            "codemap.cli.commands.index.change_counts",
            lambda root, since_days=90: {"src/B.java": 7},
        )
        _apply_hotspots(store, tmp_path)
        store.commit()
        s = store.get(sid)
    assert s is not None
    assert s.extra["change_count_90d"] == 7


def test_apply_hotspots_noop_when_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with JsonStore.open(tmp_path / ".codemap") as store:
        monkeypatch.setattr(
            "codemap.cli.commands.index.change_counts",
            lambda root, since_days=90: {},
        )
        _apply_hotspots(store, tmp_path)  # must not raise
        store.commit()


class _FakeEmitter:
    name = "fake-em"
    version = "0.1.0"

    def emit(self, store: ReadOnlyStore, ctx: EmitContext) -> EmitResult:
        return EmitResult(files_written=["out.yml"], diagnostics=[])


def test_run_emitters_invokes_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    em_reg = EmitterRegistry()
    em_reg.register(_FakeEmitter())
    monkeypatch.setattr("codemap.cli.commands.index.get_emitter_registry", lambda: em_reg)
    stats = _IndexStats()
    config = load_config(None)
    with JsonStore.open(tmp_path / ".codemap") as store:
        _run_emitters(store, tmp_path, stats, config)
        store.commit()
