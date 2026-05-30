"""Tests for the IO layer: atomic writes, file locks, manifest version checks,
and the JSON-backed SymbolStore.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from codemap.core.models import (
    SCHEMA_VERSION,
    Alias,
    Diagnostic,
    Edge,
    Manifest,
    Range,
    Route,
    Symbol,
)
from codemap.core.symbol import SymbolID
from codemap.io.atomic import atomic_write, sweep_stale_tmp_files
from codemap.io.json_store import IntegrityError, JsonStore
from codemap.io.lock import LockTimeoutError, file_lock
from codemap.io.manifest import (
    SchemaVersionError,
    check_schema_version,
    dump_manifest,
    load_manifest,
)

# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


def test_atomic_write_basic(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    with atomic_write(target) as f:
        f.write(b"hello")
    assert target.read_bytes() == b"hello"
    assert not any(p.name.startswith("out.txt.tmp.") for p in tmp_path.iterdir())


def test_atomic_write_failure_removes_tmp(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    with pytest.raises(RuntimeError, match="boom"), atomic_write(target) as f:
        f.write(b"partial")
        raise RuntimeError("boom")
    assert not target.exists()
    assert not any(p.name.startswith("out.txt.tmp.") for p in tmp_path.iterdir())


def test_atomic_write_creates_parent(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "file.txt"
    with atomic_write(nested) as f:
        f.write(b"x")
    assert nested.read_bytes() == b"x"


def test_sweep_stale_tmp_files(tmp_path: Path) -> None:
    # Simulate a crashed write: leftover .tmp.<pid> with dead pid
    dead = tmp_path / "out.json.tmp.999999"
    dead.write_bytes(b"junk")
    # Backdate so the age threshold is satisfied
    old = time.time() - 60
    os.utime(dead, (old, old))
    removed = sweep_stale_tmp_files(tmp_path, min_age_seconds=5)
    assert removed == 1
    assert not dead.exists()


def test_sweep_keeps_recent_files(tmp_path: Path) -> None:
    fresh = tmp_path / "out.json.tmp.999998"
    fresh.write_bytes(b"junk")
    removed = sweep_stale_tmp_files(tmp_path, min_age_seconds=60)
    assert removed == 0
    assert fresh.exists()


# ---------------------------------------------------------------------------
# file_lock
# ---------------------------------------------------------------------------


def test_file_lock_basic(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    with file_lock(lock, timeout=1.0):
        assert lock.exists()
        content = lock.read_text()
        assert f"pid={os.getpid()}" in content
    # Lock released — we should be able to reacquire
    with file_lock(lock, timeout=1.0):
        pass


def test_file_lock_times_out_when_held(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    ready = tmp_path / ".ready"
    holder = tmp_path / "holder.py"
    holder.write_text(
        textwrap.dedent(
            f"""
            import time
            from pathlib import Path
            from codemap.io.lock import file_lock

            with file_lock(Path({str(lock)!r}), timeout=2.0):
                Path({str(ready)!r}).write_text("x")
                time.sleep(5)
            """
        ).strip()
    )
    proc = subprocess.Popen([sys.executable, str(holder)])
    try:
        deadline = time.monotonic() + 5.0
        while not ready.exists():
            if time.monotonic() > deadline:
                pytest.fail("holder subprocess did not acquire lock in time")
            time.sleep(0.05)
        t0 = time.monotonic()
        with pytest.raises(LockTimeoutError), file_lock(lock, timeout=0.5):
            pass
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0
    finally:
        proc.kill()
        proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# Manifest / schema_version
# ---------------------------------------------------------------------------


def test_check_schema_version_accepts_current() -> None:
    check_schema_version(SCHEMA_VERSION)


def test_check_schema_version_rejects_empty() -> None:
    with pytest.raises(SchemaVersionError):
        check_schema_version("")


def test_check_schema_version_rejects_major_mismatch() -> None:
    with pytest.raises(SchemaVersionError):
        check_schema_version("999.0.0")


def test_check_schema_version_rejects_newer_minor() -> None:
    with pytest.raises(SchemaVersionError):
        check_schema_version("1.999.0")


def test_check_schema_version_warns_on_older_minor(caplog: pytest.LogCaptureFixture) -> None:
    # If current MINOR is 0, we can't construct an older-MINOR case; skip.
    if SCHEMA_VERSION.split(".")[1] == "0":
        pytest.skip("current MINOR == 0; nothing older to test")
    older = SCHEMA_VERSION.split(".")
    older[1] = str(int(older[1]) - 1)
    with caplog.at_level("WARNING"):
        check_schema_version(".".join(older))
    assert any("older" in r.message for r in caplog.records)


def test_load_manifest_rejects_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("[]")  # not a JSON object
    with pytest.raises(SchemaVersionError):
        load_manifest(tmp_path)


# ---------------------------------------------------------------------------
# JsonStore — fixtures
# ---------------------------------------------------------------------------


def _make_symbol(sid_str: str, file: str = "src/foo.py") -> Symbol:
    return Symbol(
        id=SymbolID.parse(sid_str),
        kind="function",
        language="python",
        file=PurePosixPath(file),
        range=Range(start_line=1, end_line=5),
    )


def _make_manifest() -> Manifest:
    return Manifest(
        codemap_version="0.1.0",
        project_root="/tmp/proj",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# JsonStore — happy paths
# ---------------------------------------------------------------------------


def test_open_creates_empty_store(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        assert list(store.iter_symbols()) == []
        assert list(store.iter_edges()) == []


def test_upsert_and_commit_round_trip(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        s1 = _make_symbol("scip-python . . . src/foo.py/A#")
        s2 = _make_symbol("scip-python . . . src/foo.py/B#")
        store.upsert_symbols([s1, s2])
        store.upsert_edges([Edge(source=s1.id, target=s2.id, kind="calls")])
        store.set_manifest(_make_manifest())
        store.commit()

    # Reopen and verify
    with JsonStore.open(tmp_path, mode="r") as store:
        assert store.get(s1.id) == s1
        assert store.get(s2.id) == s2
        callees = store.callees(s1.id)
        assert len(callees) == 1
        assert callees[0].target == s2.id
        callers = store.callers(s2.id)
        assert len(callers) == 1


def test_commit_writes_expected_files(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([_make_symbol("scip-python . . . src/foo.py/A#")])
        store.set_manifest(_make_manifest())
        store.commit()
    for name in (
        "manifest.json",
        "symbols.json",
        "edges.json",
        "routes.json",
        "aliases.json",
        "diagnostics.json",
    ):
        assert (tmp_path / name).exists(), name


def test_routes_aliases_diagnostics_round_trip(tmp_path: Path) -> None:
    sym = _make_symbol("scip-python . . . src/foo.py/A#")
    route = Route(method="GET", path="/api/foo", symbol_id=sym.id, context_path="/api")
    alias = Alias(
        source=SymbolID.parse("scip-mybatis . . . src/m.xml/com/foo/Mapper#m."),
        targets=[sym.id],
        producer="mybatis",
    )
    diag = Diagnostic(
        severity="warning",
        file=PurePosixPath("src/foo.py"),
        code="X001",
        message="ambiguous",
        producer="python",
    )
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([sym])
        store.upsert_routes([route])
        store.upsert_aliases([alias])
        store.upsert_diagnostics([diag])
        store.set_manifest(_make_manifest())
        store.commit()

    with JsonStore.open(tmp_path, mode="r") as store:
        manifest = store.manifest()
    assert manifest.stats.route_count == 1
    assert manifest.stats.alias_count == 1
    assert manifest.stats.diagnostic_count == 1


# ---------------------------------------------------------------------------
# JsonStore — incremental update
# ---------------------------------------------------------------------------


def test_delete_by_file_removes_symbols_edges_routes(tmp_path: Path) -> None:
    foo = _make_symbol("scip-python . . . src/foo.py/A#", file="src/foo.py")
    bar = _make_symbol("scip-python . . . src/bar.py/B#", file="src/bar.py")
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([foo, bar])
        store.upsert_edges([Edge(source=foo.id, target=bar.id, kind="calls")])
        store.set_manifest(_make_manifest())
        store.commit()

    with JsonStore.open(tmp_path) as store:
        store.delete_by_file("src/foo.py")
        store.commit()

    with JsonStore.open(tmp_path, mode="r") as store:
        assert store.get(foo.id) is None
        assert store.get(bar.id) is not None
        # Edge was anchored on foo → removed
        assert list(store.iter_edges()) == []


# ---------------------------------------------------------------------------
# JsonStore — integrity & schema enforcement
# ---------------------------------------------------------------------------


def test_load_rejects_corrupted_symbols_json(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([_make_symbol("scip-python . . . src/foo.py/A#")])
        store.set_manifest(_make_manifest())
        store.commit()
    (tmp_path / "symbols.json").write_text("not json")
    with pytest.raises(IntegrityError):
        JsonStore.open(tmp_path)


def test_load_rejects_incompatible_schema(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([_make_symbol("scip-python . . . src/foo.py/A#")])
        store.set_manifest(_make_manifest())
        store.commit()
    p = tmp_path / "manifest.json"
    data = json.loads(p.read_text())
    data["schema_version"] = "99.0.0"
    p.write_text(json.dumps(data))
    with pytest.raises(SchemaVersionError):
        JsonStore.open(tmp_path)


def test_load_rejects_high_dangling_ratio(tmp_path: Path) -> None:
    foo = _make_symbol("scip-python . . . src/foo.py/A#")
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([foo])
        # Inject an edge whose target doesn't exist
        ghost = SymbolID.parse("scip-python . . . src/ghost.py/X#")
        store.upsert_edges([Edge(source=foo.id, target=ghost, kind="calls")])
        store.set_manifest(_make_manifest())
        store.commit()
    with pytest.raises(IntegrityError):
        JsonStore.open(tmp_path)


# ---------------------------------------------------------------------------
# JsonStore — write protection
# ---------------------------------------------------------------------------


def test_readonly_mode_blocks_writes(tmp_path: Path) -> None:
    with JsonStore.open(tmp_path) as store:
        store.set_manifest(_make_manifest())
        store.commit()
    with JsonStore.open(tmp_path, mode="r") as store, pytest.raises(PermissionError):
        store.upsert_symbols([_make_symbol("scip-python . . . src/foo.py/A#")])


def test_closed_store_blocks_writes(tmp_path: Path) -> None:
    store = JsonStore.open(tmp_path)
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.upsert_symbols([_make_symbol("scip-python . . . src/foo.py/A#")])


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_matches_signature_substring(tmp_path: Path) -> None:
    sym = Symbol(
        id=SymbolID.parse("scip-python . . . src/foo.py/Foo#login()."),
        kind="method",
        language="python",
        file=PurePosixPath("src/foo.py"),
        range=Range(start_line=1, end_line=5),
        signature="def login(user, password)",
    )
    with JsonStore.open(tmp_path) as store:
        store.upsert_symbols([sym])
        store.set_manifest(_make_manifest())
        store.commit()
        hits = store.search("login")
    assert len(hits) == 1
    assert hits[0].symbol.id == sym.id


# ---------------------------------------------------------------------------
# Manifest dump utility
# ---------------------------------------------------------------------------


def test_dump_manifest_round_trip() -> None:
    m = _make_manifest()
    raw = dump_manifest(m)
    rebuilt = Manifest.model_validate_json(raw)
    assert rebuilt == m
