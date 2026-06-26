"""Tests for the knowledge freshness scorer (P4-1)."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from codemap_aimemory.freshness import (
    STALE_THRESHOLD,
    compute_freshness,
    load_code_change_map,
)

# ---------- compute_freshness ----------


def test_today_zero_code_churn_scores_one() -> None:
    today = datetime.date(2026, 6, 26)
    kn = {"updated_at": "2026-06-26", "related_code": []}
    assert compute_freshness(kn, {}, today=today) == 1.0


def test_age_180_days_halves_score() -> None:
    """180-day half-life: a knowledge updated exactly 180 days ago with
    zero code churn should land around 1/e (≈ 0.368)."""
    today = datetime.date(2026, 6, 26)
    kn = {"updated_at": "2025-12-28", "related_code": []}  # ~180 days back
    score = compute_freshness(kn, {}, today=today)
    assert 0.35 <= score <= 0.40


def test_code_churn_reduces_score() -> None:
    today = datetime.date(2026, 6, 26)
    kn = {
        "updated_at": "2026-06-26",
        "related_code": [{"file": "src/order/pricing.js"}],
    }
    # No churn → 1.0
    assert compute_freshness(kn, {}, today=today) == 1.0
    # 20 changes → code_factor = 1 / (1 + 0.05 * 20) = 0.5
    assert compute_freshness(kn, {"src/order/pricing.js": 20}, today=today) == 0.5


def test_age_and_churn_compound() -> None:
    today = datetime.date(2026, 6, 26)
    kn = {
        "updated_at": "2025-12-28",  # ~180 days back → age_factor ≈ 0.37
        "related_code": [{"file": "src/x.js"}],
    }
    score = compute_freshness(kn, {"src/x.js": 20}, today=today)
    # 0.37 * 0.5 ≈ 0.18
    assert 0.15 <= score <= 0.20


def test_future_updated_at_clamped_to_today() -> None:
    """A bad data point (updated_at in the future) shouldn't crash or
    score > 1; clamp age to 0."""
    today = datetime.date(2026, 6, 26)
    kn = {"updated_at": "2027-01-01"}
    assert compute_freshness(kn, {}, today=today) == 1.0


def test_missing_updated_at_treated_as_today() -> None:
    today = datetime.date(2026, 6, 26)
    kn: dict = {}
    assert compute_freshness(kn, {}, today=today) == 1.0


def test_malformed_updated_at_treated_as_today() -> None:
    today = datetime.date(2026, 6, 26)
    kn = {"updated_at": "not-a-date"}
    assert compute_freshness(kn, {}, today=today) == 1.0


def test_unknown_file_not_in_change_map_treated_as_zero() -> None:
    today = datetime.date(2026, 6, 26)
    kn = {
        "updated_at": "2026-06-26",
        "related_code": [{"file": "src/never/indexed.js"}],
    }
    assert compute_freshness(kn, {"src/other.js": 50}, today=today) == 1.0


def test_stale_threshold_constant() -> None:
    assert STALE_THRESHOLD == 0.5


# ---------- load_code_change_map ----------


def test_load_code_change_map_reads_functions_and_tables(tmp_path: Path) -> None:
    ai_mem = tmp_path / ".ai-memory" / "entities"
    ai_mem.mkdir(parents=True)
    (ai_mem / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {"id": "fn-a", "file": "src/a.py", "change_count_90d": 5},
                {"id": "fn-b", "file": "src/a.py", "change_count_90d": 3},
                {"id": "fn-c", "file": "src/c.py", "change_count_90d": 12},
            ]
        )
    )
    (ai_mem / "tables.yml").write_text(
        yaml.safe_dump([{"id": "tbl-x", "file": "mappers/x.xml", "change_count_90d": 7}])
    )
    m = load_code_change_map(tmp_path / ".ai-memory")
    # max wins when multiple symbols share a file
    assert m["src/a.py"] == 5
    assert m["src/c.py"] == 12
    assert m["mappers/x.xml"] == 7


def test_load_code_change_map_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_code_change_map(tmp_path / ".ai-memory") == {}


def test_load_code_change_map_skips_entries_without_file_or_count(
    tmp_path: Path,
) -> None:
    ai_mem = tmp_path / ".ai-memory" / "entities"
    ai_mem.mkdir(parents=True)
    (ai_mem / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {"id": "fn-no-file"},
                {"id": "fn-no-count", "file": "src/a.py"},
                {"id": "fn-ok", "file": "src/b.py", "change_count_90d": 4},
            ]
        )
    )
    m = load_code_change_map(tmp_path / ".ai-memory")
    assert m == {"src/b.py": 4}
