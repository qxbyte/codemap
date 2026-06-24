"""Tests for ``codemap enrich`` CLI command + LLM client builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
from codemap_aimemory.cli import register
from codemap_aimemory.llm import (
    AnthropicClient,
    OpenAICompatibleClient,
    build_client,
    env_default,
)
from typer.testing import CliRunner

from codemap.core.models import Range, Symbol
from codemap.core.symbol import SymbolID
from codemap.io.json_store import JsonStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=False)
    register(app)
    # Force typer to keep `enrich` as a named subcommand even though it's
    # the only one (typer "collapses" single-command apps otherwise).
    @app.command("_noop", hidden=True)
    def _noop() -> None:  # pragma: no cover
        pass
    return app


def _seed_index(project: Path) -> None:
    codemap_dir = project / ".codemap"
    sid = SymbolID.parse("scip-java . . . src/Svc.java/Svc#calc().")
    with JsonStore.open(codemap_dir) as store:
        store.upsert_symbols(
            [
                Symbol(
                    id=sid,
                    kind="method",
                    language="java",
                    file="src/Svc.java",
                    range=Range(start_line=1, end_line=3),
                    signature="int calc()",
                )
            ]
        )
        store.commit()


# ---------------------------------------------------------------------------
# build_client
# ---------------------------------------------------------------------------


def test_build_client_openai_default_base_url() -> None:
    c = build_client(backend="openai", model="m", api_key="k")
    assert isinstance(c, OpenAICompatibleClient)
    assert c._base_url == "https://api.openai.com/v1"  # type: ignore[attr-defined]


def test_build_client_openai_custom_base_url() -> None:
    c = build_client(backend="openai", model="m", api_key="k", base_url="http://proxy")
    assert c._base_url == "http://proxy"  # type: ignore[attr-defined]


def test_build_client_ollama_uses_local_default() -> None:
    c = build_client(backend="ollama", model="llama3", api_key="")
    assert isinstance(c, OpenAICompatibleClient)
    assert c._base_url == "http://localhost:11434/v1"  # type: ignore[attr-defined]
    assert c._api_key == "ollama"  # type: ignore[attr-defined]


def test_build_client_anthropic_picks_native_client() -> None:
    c = build_client(backend="anthropic", model="claude-x", api_key="k")
    assert isinstance(c, AnthropicClient)


def test_build_client_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="unknown LLM backend"):
        build_client(backend="weird", model="m", api_key="k")


# ---------------------------------------------------------------------------
# env_default
# ---------------------------------------------------------------------------


def test_env_default_returns_first_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEMAP_LLM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anth-key")
    assert env_default("CODEMAP_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY") == "anth-key"


def test_env_default_none_when_all_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CODEMAP_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert env_default("CODEMAP_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY") is None


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def test_cli_errors_when_no_codemap_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["enrich", str(tmp_path)])
    assert result.exit_code == 2
    assert "no .codemap/" in result.output or "no .codemap/" in (result.stderr or "")


def test_cli_dry_run_counts_method_symbols(tmp_path: Path) -> None:
    _seed_index(tmp_path)
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["enrich", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would enrich 1 function/method symbols" in result.output


def test_cli_errors_when_no_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_index(tmp_path)
    for name in ("CODEMAP_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["enrich", str(tmp_path)])
    assert result.exit_code == 2
    output = result.output + (result.stderr or "")
    assert "API key" in output


def test_cli_ollama_does_not_require_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama runs locally and does not authenticate, so the key check
    short-circuits. We monkey-patch enrich() so the test doesn't actually
    try to talk to a local Ollama (which probably isn't installed)."""
    _seed_index(tmp_path)
    called: dict[str, Any] = {}

    def fake_enrich(store, client, out_dir, *, generated_at, changed_only=False):  # type: ignore[no-untyped-def]
        called["model"] = client.model
        called["base"] = client._base_url
        return ["x.yml"]

    monkeypatch.setattr("codemap_aimemory.cli.enrich", fake_enrich)
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["enrich", str(tmp_path), "--backend", "ollama", "--model", "llama3"],
    )
    assert result.exit_code == 0, result.output
    assert called["model"] == "llama3"
    assert called["base"] == "http://localhost:11434/v1"


def test_cli_uses_explicit_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_index(tmp_path)
    captured: dict[str, Any] = {}

    def fake_enrich(store, client, out_dir, *, generated_at, changed_only=False):  # type: ignore[no-untyped-def]
        captured["base"] = client._base_url
        return []

    monkeypatch.setattr("codemap_aimemory.cli.enrich", fake_enrich)
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        [
            "enrich",
            str(tmp_path),
            "--api-key",
            "k",
            "--base-url",
            "http://my-proxy/v1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["base"] == "http://my-proxy/v1"


# ---------------------------------------------------------------------------
# OpenAICompatibleClient.describe — degradation
# ---------------------------------------------------------------------------


def test_describe_handles_network_failure_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient HTTP failures must not crash a Plan-4 pipeline. The
    client returns empty values so the enrichment file still lands with
    the correct shape."""
    import httpx

    c = OpenAICompatibleClient(model="x", api_key="k", base_url="http://nope")

    class _RaisingClient:
        def __init__(self, *a: Any, **kw: Any) -> None: ...

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_: Any) -> None: ...

        def post(self, *a: Any, **kw: Any):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "Client", _RaisingClient)
    result = c.describe({"symbol_id": "x"})
    assert result == {"business_meaning": None, "related_rules": []}
