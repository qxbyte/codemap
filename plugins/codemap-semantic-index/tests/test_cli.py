"""Tests for the ``codemap embed`` typer CLI tree (config / backend
sub-commands only; full embed pipeline is tested in test_indexer)."""

from __future__ import annotations

from pathlib import Path

import typer
from codemap_semantic_index.cli import register
from typer.testing import CliRunner


def _make_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=False)
    register(app)
    return app


def test_backend_show_with_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Make sure no env api keys bleed in from the dev machine
    for env in (
        "CODEMAP_EMBED_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "ZHIPUAI_API_KEY",
        "VOYAGE_API_KEY",
        "CODEMAP_EMBED_BACKEND",
        "CODEMAP_EMBED_BASE_URL",
        "CODEMAP_EMBED_MODEL",
    ):
        monkeypatch.delenv(env, raising=False)
    result = CliRunner().invoke(_make_app(), ["embed", "backend", "show"])
    assert result.exit_code == 0, result.stdout
    assert "backend     : local" in result.stdout
    assert "Qwen/Qwen3-Embedding-0.6B" in result.stdout
    assert "dimensions  : 1024" in result.stdout


def test_backend_set_qwen_with_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "qwen", "--api-key", "sk-test"],
    )
    assert result.exit_code == 0, result.stdout
    assert "qwen" in result.stdout
    # Verify show reads it back
    show = runner.invoke(_make_app(), ["embed", "backend", "show"])
    assert "openai_compatible" in show.stdout
    assert "qwen" in show.stdout
    assert "dashscope.aliyuncs.com" in show.stdout
    # API key should be masked
    assert "sk-test" not in show.stdout


def test_backend_set_openai_uses_dim_1024(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = CliRunner().invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "openai", "--api-key", "sk-x"],
    )
    assert result.exit_code == 0
    show = CliRunner().invoke(_make_app(), ["embed", "backend", "show"])
    assert "dimensions  : 1024" in show.stdout


def test_backend_set_qwen_picks_up_env_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "from-env")
    result = CliRunner().invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "qwen"],
    )
    assert result.exit_code == 0, result.stdout


def test_backend_set_without_api_key_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for env in ("CODEMAP_EMBED_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    result = CliRunner().invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "qwen"],
    )
    assert result.exit_code == 2
    assert "api key required" in (result.stdout + (result.stderr or "")).lower()


def test_backend_set_custom_requires_base_url_and_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("CODEMAP_EMBED_API_KEY", "k")
    result = CliRunner().invoke(_make_app(), ["embed", "backend", "set", "--provider", "custom"])
    assert result.exit_code == 2
    assert "base-url" in (result.stdout + (result.stderr or ""))


def test_backend_set_custom_full_args(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        [
            "embed",
            "backend",
            "set",
            "--provider",
            "custom",
            "--base-url",
            "http://localhost:8080/v1",
            "--api-key",
            "dummy",
            "--model",
            "my-embed",
            "--dimensions",
            "1024",
        ],
    )
    assert result.exit_code == 0, result.stdout
    show = runner.invoke(_make_app(), ["embed", "backend", "show"])
    assert "localhost:8080" in show.stdout
    assert "my-embed" in show.stdout


def test_backend_reset_returns_to_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()
    # First set to cloud
    runner.invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "qwen", "--api-key", "k"],
    )
    # Then reset
    result = runner.invoke(_make_app(), ["embed", "backend", "reset"])
    assert result.exit_code == 0
    show = runner.invoke(_make_app(), ["embed", "backend", "show"])
    assert "backend     : local" in show.stdout


def test_backend_path_prints_config_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = CliRunner().invoke(_make_app(), ["embed", "backend", "path"])
    assert result.exit_code == 0
    assert "embedding.yaml" in result.stdout


def test_backend_set_invalid_provider_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = CliRunner().invoke(
        _make_app(),
        ["embed", "backend", "set", "--provider", "unknown-provider"],
    )
    assert result.exit_code == 2
    assert "unknown provider" in (result.stdout + (result.stderr or "")).lower()


def test_install_direct_model_id(tmp_path: Path, monkeypatch) -> None:
    """`codemap embed install <model_id>` skips the interactive picker."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = CliRunner().invoke(
        _make_app(),
        ["embed", "install", "BAAI/bge-m3"],
    )
    assert result.exit_code == 0
    assert "BAAI/bge-m3" in result.stdout
    # Verify config was updated
    show = CliRunner().invoke(_make_app(), ["embed", "backend", "show"])
    assert "BAAI/bge-m3" in show.stdout
