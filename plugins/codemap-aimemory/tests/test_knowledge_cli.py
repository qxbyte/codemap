"""Tests for ``codemap knowledge {write,validate,lint}`` CLI (FIX-2)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml
from codemap_aimemory.knowledge_cli import register
from typer.testing import CliRunner


def _make_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=False)
    register(app)

    @app.command("_noop", hidden=True)
    def _noop() -> None:  # pragma: no cover
        pass

    return app


def test_write_creates_knowledge_from_payload_file(tmp_path: Path) -> None:
    (tmp_path / ".ai-memory").mkdir()
    payload = {
        "knowledge_id": "rule-coupon-mutex",
        "fields": {"statement": "优惠券和积分不能同时用"},
        "md_body": "## 规则\n\n正文\n",
    }
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(payload), encoding="utf-8")
    result = CliRunner().invoke(
        _make_app(),
        [
            "knowledge",
            "write",
            "--project",
            str(tmp_path),
            "--category",
            "rules",
            "--payload",
            str(pf),
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["knowledge_id"] == "rule-coupon-mutex"
    assert out["action"] == "created"
    assert (tmp_path / ".ai-memory/knowledge/rules/rule-coupon-mutex.yml").is_file()
    assert (tmp_path / "knowledge-base/rules/rule-coupon-mutex.md").is_file()


def test_write_reads_payload_from_stdin(tmp_path: Path) -> None:
    (tmp_path / ".ai-memory").mkdir()
    payload = {"spec_id": "REQ-001", "fields": {"implementation_summary": "x"}}
    result = CliRunner().invoke(
        _make_app(),
        [
            "knowledge",
            "write",
            "--project",
            str(tmp_path),
            "--category",
            "cases",
            "--payload",
            "-",
            "-o",
            "json",
        ],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["knowledge_id"] == "case-req-001"


def test_write_rejects_bad_category_nonzero(tmp_path: Path) -> None:
    (tmp_path / ".ai-memory").mkdir()
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"fields": {}}), encoding="utf-8")
    result = CliRunner().invoke(
        _make_app(),
        [
            "knowledge",
            "write",
            "--project",
            str(tmp_path),
            "--category",
            "bogus",
            "--payload",
            str(pf),
        ],
    )
    assert result.exit_code != 0


def test_validate_payload_dry_run_reports_errors(tmp_path: Path) -> None:
    # a payload that can't derive an id → validate exits non-zero, writes nothing
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"fields": {"statement": "x"}}), encoding="utf-8")
    result = CliRunner().invoke(
        _make_app(),
        ["knowledge", "validate", "--category", "rules", "--payload", str(pf)],
    )
    assert result.exit_code != 0


def test_lint_scans_tree_and_flags_bad_yml(tmp_path: Path) -> None:
    bad = tmp_path / ".ai-memory/knowledge/rules/rule-bad.yml"
    bad.parent.mkdir(parents=True)
    # type mismatch + missing required fields
    bad.write_text(
        yaml.safe_dump({"knowledge_id": "rule-bad", "type": "pitfall"}), encoding="utf-8"
    )
    result = CliRunner().invoke(
        _make_app(),
        ["knowledge", "lint", "--project", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "rule-bad" in result.stdout


def test_lint_clean_tree_exits_zero(tmp_path: Path) -> None:
    (tmp_path / ".ai-memory").mkdir()
    # write a valid one first via the writer path
    pf = tmp_path / "p.json"
    pf.write_text(
        json.dumps({"knowledge_id": "rule-ok", "fields": {"statement": "s"}}), encoding="utf-8"
    )
    CliRunner().invoke(
        _make_app(),
        [
            "knowledge",
            "write",
            "--project",
            str(tmp_path),
            "--category",
            "rules",
            "--payload",
            str(pf),
        ],
    )
    result = CliRunner().invoke(_make_app(), ["knowledge", "lint", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
