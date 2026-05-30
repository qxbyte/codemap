"""Unit tests for ``codemap.config`` — schema, loader, merging."""

from __future__ import annotations

from pathlib import Path

import pytest

from codemap.config import Config, ConfigError, dump_config, load_config
from codemap.config.schema import DEFAULT_MAX_FILE_BYTES

# ---------------------------------------------------------------------------
# Schema defaults
# ---------------------------------------------------------------------------


def test_default_config_is_self_consistent() -> None:
    c = Config()
    assert c.storage.backend == "json"
    assert c.index.ignore == []
    assert c.index.max_file_bytes == DEFAULT_MAX_FILE_BYTES
    assert c.index.follow_symlinks is False
    assert c.indexers.enabled == "all"
    assert c.indexers.disabled == []
    assert c.bridges.enabled == "all"
    assert c.bridges.disabled == []


def test_schema_rejects_unknown_top_level_key() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config.model_validate({"storaeg": {"backend": "json"}})  # typo


def test_schema_rejects_unknown_backend() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config.model_validate({"storage": {"backend": "redis"}})


def test_schema_rejects_negative_max_file_bytes() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config.model_validate({"index": {"max_file_bytes": 0}})


def test_indexers_enabled_accepts_list_or_literal_all() -> None:
    c1 = Config.model_validate({"indexers": {"enabled": "all"}})
    c2 = Config.model_validate({"indexers": {"enabled": ["python"]}})
    assert c1.indexers.enabled == "all"
    assert c2.indexers.enabled == ["python"]


# ---------------------------------------------------------------------------
# Loader: empty / missing / malformed
# ---------------------------------------------------------------------------


def test_load_with_no_files_returns_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    c = load_config(codemap_dir=None)
    assert c == Config()


def test_load_with_project_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "config.yaml").write_text("storage:\n  backend: sqlite\nindex:\n  ignore: ['*.bak']\n")
    c = load_config(codemap_dir=cmdir)
    assert c.storage.backend == "sqlite"
    assert c.index.ignore == ["*.bak"]


def test_load_with_empty_file_returns_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "config.yaml").write_text("")
    c = load_config(codemap_dir=cmdir)
    assert c == Config()


def test_load_rejects_root_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "config.yaml").write_text("- not a mapping\n")
    with pytest.raises(ConfigError, match="mapping at the root"):
        load_config(codemap_dir=cmdir)


def test_load_rejects_malformed_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "config.yaml").write_text("storage: {backend: 'json'\n")  # unterminated brace
    with pytest.raises(ConfigError, match="failed to parse"):
        load_config(codemap_dir=cmdir)


def test_load_validation_error_lists_field_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    cmdir = tmp_path / ".codemap"
    cmdir.mkdir()
    (cmdir / "config.yaml").write_text("storage:\n  backend: redis\n")
    with pytest.raises(ConfigError, match=r"storage\.backend"):
        load_config(codemap_dir=cmdir)


# ---------------------------------------------------------------------------
# Loader: layer merging
# ---------------------------------------------------------------------------


def test_project_overrides_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    user_dir = fake_home / ".config" / "codemap"
    user_dir.mkdir(parents=True)
    (user_dir / "config.yaml").write_text(
        "storage:\n  backend: json\nindex:\n  max_file_bytes: 5000\n"
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    cmdir = tmp_path / "project" / ".codemap"
    cmdir.mkdir(parents=True)
    (cmdir / "config.yaml").write_text("index:\n  max_file_bytes: 9000\n")

    c = load_config(codemap_dir=cmdir)
    # Project's max_file_bytes wins; user's storage.backend remains
    assert c.index.max_file_bytes == 9000
    assert c.storage.backend == "json"


def test_user_provides_defaults_when_project_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    user_dir = fake_home / ".config" / "codemap"
    user_dir.mkdir(parents=True)
    (user_dir / "config.yaml").write_text("indexers:\n  disabled: ['_example_lang']\n")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    cmdir = tmp_path / "project" / ".codemap"
    cmdir.mkdir(parents=True)
    (cmdir / "config.yaml").write_text("storage:\n  backend: sqlite\n")

    c = load_config(codemap_dir=cmdir)
    assert c.indexers.disabled == ["_example_lang"]
    assert c.storage.backend == "sqlite"


def test_codemap_dir_none_skips_project_layer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    user_dir = fake_home / ".config" / "codemap"
    user_dir.mkdir(parents=True)
    (user_dir / "config.yaml").write_text("storage:\n  backend: sqlite\n")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    c = load_config(codemap_dir=None)
    assert c.storage.backend == "sqlite"  # user-level still applies


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------


def test_dump_config_round_trip() -> None:
    c = Config.model_validate(
        {
            "storage": {"backend": "sqlite"},
            "index": {"ignore": ["*.bak"], "max_file_bytes": 5000},
            "indexers": {"disabled": ["_example_lang"]},
        }
    )
    rendered = dump_config(c)
    assert "backend: sqlite" in rendered
    assert "*.bak" in rendered
    assert "5000" in rendered
