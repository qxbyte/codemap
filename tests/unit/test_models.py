"""Tests for `codemap.core.models` — schema_version, validation, JSON round-trip."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from codemap.core.models import (
    SCHEMA_VERSION,
    Alias,
    Diagnostic,
    Edge,
    FileEntry,
    IndexResult,
    Manifest,
    Range,
    Route,
    Symbol,
)
from codemap.core.symbol import SymbolID

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sym(s: str = "scip-python . . . src/foo.py/Bar#") -> SymbolID:
    return SymbolID.parse(s)


def _range(start: int = 1, end: int = 5) -> Range:
    return Range(start_line=start, end_line=end)


# ---------------------------------------------------------------------------
# Range
# ---------------------------------------------------------------------------


def test_range_basic() -> None:
    r = Range(start_line=1, end_line=10)
    assert r.start_line == 1
    assert r.end_col == 0


def test_range_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        Range(start_line=10, end_line=5)


def test_range_rejects_negative_line() -> None:
    with pytest.raises(ValidationError):
        Range(start_line=0, end_line=5)


# ---------------------------------------------------------------------------
# Symbol / Edge
# ---------------------------------------------------------------------------


def test_symbol_minimal_construction() -> None:
    sym = Symbol(
        id=_sym(),
        kind="class",
        language="python",
        file=PurePosixPath("src/foo.py"),
        range=_range(),
    )
    assert sym.confidence == "high"
    assert sym.extra == {}


def test_symbol_round_trip_json() -> None:
    sym = Symbol(
        id=_sym(),
        kind="method",
        language="python",
        file=PurePosixPath("src/foo.py"),
        range=Range(start_line=10, start_col=4, end_line=20, end_col=0),
        signature="def bar(self) -> None",
        doc="docstring",
        confidence="medium",
        extra={"async": True},
    )
    raw = sym.model_dump_json()
    rebuilt = Symbol.model_validate_json(raw)
    assert rebuilt == sym
    # SymbolID round-trips as a flat string, not a nested object
    assert "scip-python" in raw


def test_symbol_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Symbol(
            id=_sym(),
            kind="invalid-kind",  # type: ignore[arg-type]
            language="python",
            file=PurePosixPath("src/foo.py"),
            range=_range(),
        )


def test_symbol_extra_fields_forbidden() -> None:
    # `model_config.extra = "forbid"` blocks accidental drift.
    with pytest.raises(ValidationError):
        Symbol.model_validate(
            {
                "id": "scip-python . . . src/foo.py/Bar#",
                "kind": "class",
                "language": "python",
                "file": "src/foo.py",
                "range": {"start_line": 1, "end_line": 5},
                "unknown_field": "x",
            }
        )


def test_edge_round_trip() -> None:
    e = Edge(
        source=_sym(),
        target=_sym("scip-python . . . src/bar.py/Baz#"),
        kind="calls",
        confidence="high",
    )
    raw = e.model_dump_json()
    assert Edge.model_validate_json(raw) == e


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------


def test_diagnostic_required_fields() -> None:
    d = Diagnostic(
        severity="warning",
        file=PurePosixPath("src/foo.py"),
        code="PY001",
        message="ambiguous import",
        producer="python",
    )
    assert d.range is None


def test_diagnostic_rejects_bad_severity() -> None:
    with pytest.raises(ValidationError):
        Diagnostic(
            severity="critical",  # type: ignore[arg-type]
            file=PurePosixPath("src/foo.py"),
            code="X",
            message="x",
            producer="x",
        )


# ---------------------------------------------------------------------------
# FileEntry / Manifest
# ---------------------------------------------------------------------------


def test_file_entry_requires_64_char_sha() -> None:
    with pytest.raises(ValidationError):
        FileEntry(
            sha256="too short",
            mtime_ns=0,
            size=0,
            language="python",
            indexer_version="0.1.0",
            symbol_count=0,
            indexed_at=datetime.now(UTC),
        )


def test_manifest_defaults_to_current_schema_version() -> None:
    m = Manifest(
        codemap_version="0.1.0",
        project_root="/tmp/proj",
    )
    assert m.schema_version == SCHEMA_VERSION
    assert m.stats.symbol_count == 0
    assert m.indexers == []
    assert m.storage_backend == "json"


def test_manifest_round_trip_json() -> None:
    m = Manifest(
        codemap_version="0.1.0",
        project_root="/tmp/proj",
    )
    raw = m.model_dump_json()
    assert Manifest.model_validate_json(raw) == m
    assert f'"schema_version":"{SCHEMA_VERSION}"' in raw


def test_manifest_rejects_unknown_backend() -> None:
    with pytest.raises(ValidationError):
        Manifest(
            codemap_version="0.1.0",
            project_root="/tmp/proj",
            storage_backend="redis",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Bridge outputs
# ---------------------------------------------------------------------------


def test_route_and_alias_round_trip() -> None:
    r = Route(
        method="GET",
        path="/api/user/list",
        symbol_id=_sym(),
        context_path="/api",
    )
    a = Alias(
        source=_sym("scip-mybatis local . . src/m.xml/com/foo/Mapper#m."),
        targets=[_sym("scip-java local . . src/m.java/Mapper#m().")],
        producer="mybatis",
        confidence="high",
    )
    assert Route.model_validate_json(r.model_dump_json()) == r
    assert Alias.model_validate_json(a.model_dump_json()) == a


# ---------------------------------------------------------------------------
# IndexResult composition
# ---------------------------------------------------------------------------


def test_index_result_empty_by_default() -> None:
    r = IndexResult()
    assert r.symbols == []
    assert r.edges == []
    assert r.routes == []
    assert r.diagnostics == []


def test_index_result_with_data_round_trip() -> None:
    sym = Symbol(
        id=_sym(),
        kind="class",
        language="python",
        file=PurePosixPath("src/foo.py"),
        range=_range(),
    )
    edge = Edge(source=_sym(), target=_sym("scip-python . . . src/b.py/X#"), kind="references")
    r = IndexResult(symbols=[sym], edges=[edge])
    raw = r.model_dump_json()
    rebuilt = IndexResult.model_validate_json(raw)
    assert rebuilt == r
