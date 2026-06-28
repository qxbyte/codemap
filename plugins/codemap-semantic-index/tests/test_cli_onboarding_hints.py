"""Regression tests for v0.9 痛点 #5 / #15 / #16 — embed onboarding hints.

Real-world try-run on 2026-06-28 found 3 onboarding gaps in `codemap embed`:

- #15: first run (no `embed install` yet) silently downloads 1.2GB Qwen3
       model — no "will download X, confirm?" prompt, no model-picker
- #16: HuggingFace Hub direct from mainland China hangs at 0 bytes —
       no hint to set HF_ENDPOINT=https://hf-mirror.com
- #5:  empty knowledge-base/ shows `total 0` cryptically — no hint that
       the user must run specode-distill / task-swarm first

This file pins the user-facing copy of these hints so future refactors
can't silently regress them.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from codemap_semantic_index import cli, config
from typer.testing import CliRunner


@pytest.fixture
def app():
    import typer

    app = typer.Typer()
    cli.register(app)
    return app


@pytest.fixture
def runner():
    # Newer Click/Typer dropped `mix_stderr=False`; output captures both
    # stdout and stderr in `result.output`. We check `result.output` everywhere.
    return CliRunner()


class _FakeBackend:
    """Pretend backend so we don't pull torch into tests."""

    dimensions = 4
    model_id = "local:huggingface:Qwen/Qwen3-Embedding-0.6B"
    model = "Qwen/Qwen3-Embedding-0.6B"

    def encode(self, texts):
        return np.zeros((len(texts), self.dimensions), dtype=np.float32)


def test_first_run_warns_about_1gb_download(app, runner, tmp_path, monkeypatch):
    """v0.9 痛点 #15 — first run without `embed install` must warn before
    the (silent) ~1.2GB model download starts."""
    # No config file (= first run)
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "embedding.yaml")
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    # Project with no knowledge-base so we don't actually call encode
    project = tmp_path / "proj"
    project.mkdir()

    with (
        patch("codemap_semantic_index.cli._model_cached", return_value=False),
        patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()),
    ):
        result = runner.invoke(app, ["embed", "--project", str(project), "--dry-run"])

    # Find the hint somewhere in stderr (echo with err=True).
    stderr_blob = result.output or ""
    assert "First-time embed" in stderr_blob or "first" in stderr_blob.lower(), (
        f"#15 hint missing from stderr. Got: {stderr_blob[:500]}"
    )
    assert "1.2GB" in stderr_blob or "1.19" in stderr_blob or "GB" in stderr_blob, (
        f"#15 hint should mention model size. Got: {stderr_blob[:500]}"
    )


def test_first_run_hints_hf_mirror_when_no_HF_ENDPOINT(app, runner, tmp_path, monkeypatch):
    """v0.9 痛点 #16 — when HF_ENDPOINT is not set and we're about to
    download from hf.co, emit a CN-mirror hint (国内必踩)."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "embedding.yaml")
    monkeypatch.delenv("HF_ENDPOINT", raising=False)

    project = tmp_path / "proj"
    project.mkdir()

    with (
        patch("codemap_semantic_index.cli._model_cached", return_value=False),
        patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()),
    ):
        result = runner.invoke(app, ["embed", "--project", str(project), "--dry-run"])

    stderr_blob = result.output or ""
    assert "hf-mirror.com" in stderr_blob, (
        f"#16 hint missing — expected hf-mirror.com workaround text. Got: {stderr_blob[:500]}"
    )
    assert "HF_ENDPOINT" in stderr_blob


def test_no_hint_when_HF_ENDPOINT_already_set(app, runner, tmp_path, monkeypatch):
    """If user already set HF_ENDPOINT, don't pester them with the mirror
    hint — they clearly know."""
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "embedding.yaml")
    monkeypatch.setenv("HF_ENDPOINT", "https://hf-mirror.com")

    project = tmp_path / "proj"
    project.mkdir()

    with (
        patch("codemap_semantic_index.cli._model_cached", return_value=False),
        patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()),
    ):
        result = runner.invoke(app, ["embed", "--project", str(project), "--dry-run"])

    stderr_blob = result.output or ""
    assert "hf-mirror.com" not in stderr_blob, (
        f"#16 hint should NOT appear when HF_ENDPOINT already set. Got: {stderr_blob[:500]}"
    )


def test_no_hint_when_config_exists(app, runner, tmp_path, monkeypatch):
    """If config exists (= user ran `embed install`), they already know
    they're using a local model — no need for first-run warning."""
    cfg_path = tmp_path / "embedding.yaml"
    cfg_path.write_text("backend: local\nmodel: Qwen/Qwen3-Embedding-0.6B\n")
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)

    project = tmp_path / "proj"
    project.mkdir()

    with (
        patch("codemap_semantic_index.cli._model_cached", return_value=False),
        patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()),
    ):
        result = runner.invoke(app, ["embed", "--project", str(project), "--dry-run"])

    stderr_blob = result.output or ""
    assert "First-time" not in stderr_blob, (
        f"#15 hint should NOT appear when user already ran install. Got: {stderr_blob[:500]}"
    )


def test_empty_kb_emits_specific_hint_when_dir_missing(app, runner, tmp_path, monkeypatch):
    """v0.9 痛点 #5 — `total 0` should be paired with an explanation when
    knowledge-base/ doesn't exist."""
    cfg_path = tmp_path / "embedding.yaml"
    cfg_path.write_text("backend: local\nmodel: x\n")
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)

    project = tmp_path / "proj"
    project.mkdir()
    # No knowledge-base/ inside project

    with patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()):
        result = runner.invoke(app, ["embed", "--project", str(project)])

    stderr_blob = result.output or ""
    assert "knowledge-base" in stderr_blob, (
        f"#5 hint missing — expected to mention knowledge-base/. Got: {stderr_blob[:500]}"
    )
    assert "specode-distill" in stderr_blob or "task-swarm" in stderr_blob, (
        f"#5 hint should explain where chunks come from. Got: {stderr_blob[:500]}"
    )


def test_empty_kb_emits_specific_hint_when_dir_empty(app, runner, tmp_path, monkeypatch):
    """#5 variant — knowledge-base/ exists but has no .md files."""
    cfg_path = tmp_path / "embedding.yaml"
    cfg_path.write_text("backend: local\nmodel: x\n")
    monkeypatch.setattr(config, "config_path", lambda: cfg_path)

    project = tmp_path / "proj"
    (project / "knowledge-base").mkdir(parents=True)

    with patch("codemap_semantic_index.cli.build_backend", return_value=_FakeBackend()):
        result = runner.invoke(app, ["embed", "--project", str(project)])

    stderr_blob = result.output or ""
    assert "knowledge-base" in stderr_blob
    assert "no .md" in stderr_blob or "no markdown" in stderr_blob.lower(), (
        f"#5 hint should distinguish 'dir missing' vs 'dir empty'. Got: {stderr_blob[:500]}"
    )
