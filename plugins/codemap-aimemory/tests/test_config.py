"""Tests for ``codemap_aimemory.config`` + ``codemap llm config`` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
import yaml
from codemap_aimemory.config import LlmConfig, config_path, load, save, unset
from codemap_aimemory.llm_cli import register
from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=False)
    register(app)

    # Force typer to keep `llm` as a named subcommand even though it's the
    # only one mounted here (typer otherwise "collapses" single-command apps).
    @app.command("_noop", hidden=True)
    def _noop() -> None:  # pragma: no cover
        pass

    return app


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``config_path()`` to tmp by setting XDG_CONFIG_HOME."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "codemap" / "llm.yaml"


# ---------------------------------------------------------------------------
# config_path / XDG handling
# ---------------------------------------------------------------------------


def test_config_path_uses_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "codemap" / "llm.yaml"


def test_config_path_falls_back_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config_path() == Path.home() / ".config" / "codemap" / "llm.yaml"


# ---------------------------------------------------------------------------
# load / save round-trip
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(isolated_config: Path) -> None:
    assert load() == LlmConfig()


def test_save_and_load_round_trip(isolated_config: Path) -> None:
    cfg = LlmConfig(
        backend="openai",
        model="deepseek-chat",
        api_key="sk-xxx",
        base_url="https://api.deepseek.com/v1",
    )
    save(cfg)
    assert load() == cfg


def test_save_writes_chmod_600(isolated_config: Path) -> None:
    save(LlmConfig(api_key="sk-x"))
    mode = isolated_config.stat().st_mode & 0o777
    assert mode == 0o600, f"expected mode 600, got {mode:o}"


def test_save_omits_none_fields(isolated_config: Path) -> None:
    save(LlmConfig(api_key="sk-x"))
    data = yaml.safe_load(isolated_config.read_text())
    assert data == {"api_key": "sk-x"}


def test_load_ignores_unknown_keys(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True, exist_ok=True)
    isolated_config.write_text(yaml.safe_dump({"backend": "openai", "weird_key": "x"}))
    assert load() == LlmConfig(backend="openai")


def test_load_corrupt_yaml_returns_empty(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True, exist_ok=True)
    isolated_config.write_text("not: : valid: yaml: at: all: [[[")
    assert load() == LlmConfig()


def test_unset_clears_field(isolated_config: Path) -> None:
    save(LlmConfig(api_key="sk-x", model="m"))
    unset("api_key")
    assert load() == LlmConfig(model="m")


def test_unset_unknown_key_raises(isolated_config: Path) -> None:
    with pytest.raises(ValueError, match="unknown config key"):
        unset("invalid_field")


# ---------------------------------------------------------------------------
# merged_with priority
# ---------------------------------------------------------------------------


def test_merged_with_override_wins() -> None:
    base = LlmConfig(backend="openai", model="gpt-4o-mini", api_key="old")
    override = LlmConfig(api_key="new")
    merged = base.merged_with(override)
    assert merged == LlmConfig(backend="openai", model="gpt-4o-mini", api_key="new")


def test_merged_with_none_does_not_override() -> None:
    base = LlmConfig(backend="openai", api_key="keep")
    override = LlmConfig(model="new-model")  # api_key is None → keep `base`
    merged = base.merged_with(override)
    assert merged.api_key == "keep"
    assert merged.model == "new-model"


# ---------------------------------------------------------------------------
# CLI: codemap llm config show / set / unset / path
# ---------------------------------------------------------------------------


def test_cli_set_persists(isolated_config: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "set", "api-key", "sk-secret-12345"])
    assert result.exit_code == 0, result.output
    assert load().api_key == "sk-secret-12345"
    # API key shown masked, never in full
    assert "sk-secret-12345" not in result.output
    assert "sk-s" in result.output


def test_cli_set_accepts_both_dash_and_underscore(isolated_config: Path) -> None:
    runner = CliRunner()
    for key in ("api-key", "api_key", "base-url", "base_url"):
        result = runner.invoke(_make_app(), ["llm", "config", "set", key, "v"])
        assert result.exit_code == 0, f"{key}: {result.output}"


def test_cli_set_unknown_key_errors(isolated_config: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "set", "totally-bogus", "v"])
    assert result.exit_code == 2
    assert "unknown key" in (result.output + (result.stderr or ""))


def test_cli_show_marks_sources(isolated_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # File supplies model; env supplies api-key; defaults supply backend.
    save(LlmConfig(model="from-file"))
    monkeypatch.setenv("CODEMAP_LLM_API_KEY", "env-key-value")
    for n in ("CODEMAP_LLM_BACKEND", "CODEMAP_LLM_MODEL", "CODEMAP_LLM_BASE_URL"):
        monkeypatch.delenv(n, raising=False)
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "show"])
    assert result.exit_code == 0, result.output
    assert "[default]" in result.output  # backend
    assert "[file]" in result.output  # model
    assert "[env]" in result.output  # api_key


def test_cli_path_prints_target(isolated_config: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "path"])
    assert result.exit_code == 0
    assert str(isolated_config) in result.output


def test_cli_unset_clears(isolated_config: Path) -> None:
    save(LlmConfig(api_key="sk-x", model="m"))
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "unset", "api-key"])
    assert result.exit_code == 0, result.output
    assert load() == LlmConfig(model="m")


def test_cli_unset_when_no_file_is_noop(isolated_config: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["llm", "config", "unset", "api-key"])
    assert result.exit_code == 0
    assert "nothing to unset" in result.output.lower()
