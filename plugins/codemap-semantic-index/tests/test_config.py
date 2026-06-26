"""Tests for ``embedding.yaml`` config read/write."""

from __future__ import annotations

from pathlib import Path

from codemap_semantic_index import config


def test_defaults_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.load()
    assert cfg.backend == "local"
    assert cfg.model == config.DEFAULT_LOCAL_MODEL
    assert cfg.dimensions == config.DEFAULT_DIMENSIONS


def test_save_then_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.EmbeddingConfig(
        backend="openai_compatible",
        provider="qwen",
        model="text-embedding-v3",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-xxx",
        dimensions=1024,
    )
    path = config.save(cfg)
    assert path.is_file()

    back = config.load()
    assert back.backend == "openai_compatible"
    assert back.provider == "qwen"
    assert back.api_key == "sk-xxx"
    assert back.dimensions == 1024


def test_save_sets_chmod_600(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.EmbeddingConfig(api_key="secret")
    path = config.save(cfg)
    mode = path.stat().st_mode & 0o777
    # Owner read/write only
    assert mode == 0o600


def test_unset_field(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.EmbeddingConfig(api_key="secret", provider="qwen", backend="openai_compatible")
    config.save(cfg)
    config.unset("api_key")
    back = config.load()
    assert back.api_key is None
    assert back.provider == "qwen"  # unrelated field untouched


def test_unset_backend_reverts_to_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = config.EmbeddingConfig(
        backend="openai_compatible",
        api_key="x",
        base_url="https://example.com/v1",
        model="foo",
    )
    config.save(cfg)
    config.unset("backend")
    back = config.load()
    assert back.backend == "local"
    assert back.model == config.DEFAULT_LOCAL_MODEL


def test_env_default_first_non_empty_wins(monkeypatch) -> None:
    monkeypatch.setenv("FOO", "")
    monkeypatch.setenv("BAR", "from-bar")
    monkeypatch.setenv("BAZ", "from-baz")
    assert config.env_default("FOO", "BAR", "BAZ") == "from-bar"


def test_env_default_returns_none_when_all_empty(monkeypatch) -> None:
    monkeypatch.delenv("X1", raising=False)
    monkeypatch.delenv("X2", raising=False)
    assert config.env_default("X1", "X2") is None


def test_corrupt_yaml_falls_back_to_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not: valid: ::: yaml :::!", encoding="utf-8")
    cfg = config.load()
    assert cfg.backend == "local"
    assert cfg.model == config.DEFAULT_LOCAL_MODEL


def test_to_dict_omits_none_fields() -> None:
    cfg = config.EmbeddingConfig()  # backend=local, no api_key/base_url
    d = cfg.to_dict()
    assert "api_key" not in d
    assert "base_url" not in d
    assert "provider" not in d
    assert d["backend"] == "local"
    assert d["model"] == config.DEFAULT_LOCAL_MODEL
