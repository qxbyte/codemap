"""Tests for FIX-3d — recall config (~/.config/codemap/recall.yaml).

Carries the opt-in shared knowledge roots a team can point recall at
for cross-project shared rules / pitfalls.
"""

from __future__ import annotations

from pathlib import Path

from codemap_aimemory.recall_config import (
    RecallConfig,
    config_path,
    load,
    save,
)


def test_default_config_is_empty(tmp_path: Path) -> None:
    cfg = load(tmp_path / "recall.yaml")
    assert cfg.shared_roots == ()


def test_save_load_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "recall.yaml"
    save(RecallConfig(shared_roots=("/team/knowledge", "/org/wiki")), target)
    cfg = load(target)
    assert cfg.shared_roots == ("/team/knowledge", "/org/wiki")


def test_save_skips_empty_lists(tmp_path: Path) -> None:
    target = tmp_path / "recall.yaml"
    save(RecallConfig(shared_roots=()), target)
    # File still exists but is empty / just an empty doc.
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "shared_roots" not in text or "shared_roots: []" not in text


def test_load_ignores_unknown_keys(tmp_path: Path) -> None:
    target = tmp_path / "recall.yaml"
    target.write_text(
        "shared_roots:\n  - /a\nfuture_flag: 42\n",
        encoding="utf-8",
    )
    cfg = load(target)
    assert cfg.shared_roots == ("/a",)


def test_load_malformed_file_returns_default(tmp_path: Path) -> None:
    target = tmp_path / "recall.yaml"
    target.write_text(":::not-valid:::yaml", encoding="utf-8")
    cfg = load(target)
    assert cfg.shared_roots == ()


def test_config_path_under_xdg(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "codemap" / "recall.yaml"
