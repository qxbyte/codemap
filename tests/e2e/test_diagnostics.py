"""End-to-end tests for ``codemap diagnostics``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app
from codemap.core.models import Diagnostic, Manifest, Range
from codemap.io.json_store import JsonStore

runner = CliRunner()


@pytest.fixture
def project_with_diagnostics(tmp_path: Path) -> Path:
    """A project with hand-seeded diagnostics across severities / producers."""
    proj = tmp_path / "proj"
    proj.mkdir()
    cmdir = proj / ".codemap"
    with JsonStore.open(cmdir) as store:
        store.upsert_diagnostics(
            [
                Diagnostic(
                    severity="error",
                    file=PurePosixPath("a.py"),
                    range=Range(start_line=10, end_line=10),
                    code="PY001",
                    message="syntax error: unexpected EOF",
                    producer="python",
                ),
                Diagnostic(
                    severity="warning",
                    file=PurePosixPath("b.py"),
                    code="PY002",
                    message="not valid UTF-8",
                    producer="python",
                ),
                Diagnostic(
                    severity="warning",
                    file=PurePosixPath("server.py"),
                    code="ROUTE001",
                    message="multiple handlers registered for GET /api/x",
                    producer="http_route",
                ),
                Diagnostic(
                    severity="info",
                    file=PurePosixPath("c.py"),
                    code="PY100",
                    message="informational",
                    producer="python",
                ),
            ]
        )
        store.set_manifest(
            Manifest(
                codemap_version="0.1.0",
                project_root=str(proj.resolve()),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        store.commit()
    return proj


def test_diagnostics_empty_project_friendly_message(tmp_path: Path) -> None:
    proj = tmp_path / "empty"
    proj.mkdir()
    with JsonStore.open(proj / ".codemap") as store:
        store.set_manifest(
            Manifest(
                codemap_version="0.1.0",
                project_root=str(proj),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        store.commit()
    result = runner.invoke(app, ["diagnostics", "--project", str(proj)])
    assert result.exit_code == 0
    assert "No diagnostics" in result.stdout


def test_diagnostics_lists_all_by_default(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app, ["--json", "diagnostics", "--project", str(project_with_diagnostics)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["total"] == 4
    assert payload["result"]["matched"] == 4
    assert payload["result"]["shown"] == 4


def test_diagnostics_filter_by_severity(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "diagnostics",
            "--severity",
            "warning",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["matched"] == 2
    assert {d["severity"] for d in payload["result"]["results"]} == {"warning"}


def test_diagnostics_filter_by_producer(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "diagnostics",
            "--producer",
            "http_route",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["matched"] == 1
    assert payload["result"]["results"][0]["code"] == "ROUTE001"


def test_diagnostics_filter_by_code(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "diagnostics",
            "--code",
            "PY001",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["matched"] == 1
    assert payload["result"]["results"][0]["severity"] == "error"
    assert payload["result"]["results"][0]["line"] == 10


def test_diagnostics_combined_filters(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "diagnostics",
            "--severity",
            "warning",
            "--producer",
            "python",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["matched"] == 1
    assert payload["result"]["results"][0]["code"] == "PY002"


def test_diagnostics_limit_truncates(project_with_diagnostics: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--json",
            "diagnostics",
            "--limit",
            "2",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["result"]["matched"] == 4
    assert payload["result"]["shown"] == 2


def test_diagnostics_text_output_colours_severity(project_with_diagnostics: Path) -> None:
    result = runner.invoke(app, ["diagnostics", "--project", str(project_with_diagnostics)])
    assert result.exit_code == 0
    # Rich strips color codes by default in CliRunner, but the words appear.
    assert "error" in result.stdout
    assert "warning" in result.stdout
    assert "info" in result.stdout


def test_diagnostics_filter_with_no_match_friendly(
    project_with_diagnostics: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "diagnostics",
            "--code",
            "DOES_NOT_EXIST",
            "--project",
            str(project_with_diagnostics),
        ],
    )
    assert result.exit_code == 0
    assert "No diagnostics matched" in result.stdout
