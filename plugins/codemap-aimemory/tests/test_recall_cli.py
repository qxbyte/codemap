"""Tests for ``codemap recall`` CLI — including the --from-spec shape."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml
from codemap_aimemory.recall_cli import register
from typer.testing import CliRunner


def _make_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=False)
    register(app)

    @app.command("_noop", hidden=True)
    def _noop() -> None:  # pragma: no cover - force named subcommand
        pass

    return app


def _seed_ai_memory(root: Path) -> None:
    (root / ".ai-memory" / "knowledge" / "rules").mkdir(parents=True)
    (root / ".ai-memory" / "knowledge" / "pitfalls").mkdir(parents=True)


def _write_yml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


# ---------- positional query (existing behaviour) ----------


def test_positional_query_still_works(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {"knowledge_id": "rule-coupon-mutex", "title": "优惠券互斥"},
    )
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["recall", "优惠券", "-p", str(tmp_path), "-o", "json"])
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["knowledge"]
    assert parsed["knowledge"][0]["knowledge_id"] == "rule-coupon-mutex"


# ---------- --from-spec ----------


def test_from_spec_reads_file_and_uses_as_query(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {"knowledge_id": "rule-coupon-mutex", "title": "优惠券和积分互斥"},
    )
    spec_path = tmp_path / "requirements.md"
    spec_path.write_text(
        "---\nspec_id: REQ-2026-0001\nproject_root: /abs/path\n---\n\n"
        "# 新增优惠券抵扣场景\n\n## 背景\n新优惠券需要支持叠加积分使用。",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "--from-spec", str(spec_path), "-p", str(tmp_path), "-o", "json"],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert parsed["from_spec"] == str(spec_path)
    assert parsed["query"] == f"<from-spec:{spec_path.name}>"
    # spec mentions 优惠券 — rule-coupon-mutex should surface
    assert any(k["knowledge_id"] == "rule-coupon-mutex" for k in parsed["knowledge"])


def test_from_spec_yaml_output_includes_from_spec_field(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("# anything", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "--from-spec", str(spec_path), "-p", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout
    parsed = yaml.safe_load(result.stdout)
    assert "from_spec" in parsed
    assert parsed["from_spec"] == str(spec_path)


# ---------- error paths ----------


def test_error_when_both_query_and_from_spec(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("# x", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "some-query", "--from-spec", str(spec_path), "-p", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.stdout + result.stderr


def test_error_when_neither_query_nor_from_spec(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["recall", "-p", str(tmp_path)])
    assert result.exit_code == 2
    assert "must provide" in result.stdout + result.stderr


def test_error_when_from_spec_path_missing(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "--from-spec", str(tmp_path / "nope.md"), "-p", str(tmp_path)],
    )
    # typer's exists=True triggers UsageError(2) before our body runs
    assert result.exit_code == 2


def test_error_when_no_ai_memory_dir(tmp_path: Path) -> None:
    # explicitly NO .ai-memory/ seeding
    runner = CliRunner()
    result = runner.invoke(_make_app(), ["recall", "foo", "-p", str(tmp_path)])
    assert result.exit_code == 2
    assert ".ai-memory" in result.stdout + result.stderr


# ---------- filter passthrough ----------


def test_with_content_flag_surfaces_rule_fields(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-coupon.yml",
        {
            "knowledge_id": "rule-coupon-mutex",
            "type": "business_rule",
            "title": "优惠券和积分互斥",
            "statement": "Coupons and points can't both apply.",
            "why": "Prevents stacking discounts.",
        },
    )
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "coupon", "-p", str(tmp_path), "-c", "-o", "json"],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    item = parsed["knowledge"][0]
    assert "content" in item
    assert "Coupons and points" in item["content"]["statement"]
    assert "Prevents stacking" in item["content"]["why"]
    # P4-1/P4-2 fields always emitted
    assert "freshness_score" in item
    assert "ranked_score" in item
    assert "stale" in item


def test_with_content_short_flag(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-x.yml",
        {"knowledge_id": "rule-x", "title": "X", "statement": "stmt"},
    )
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        ["recall", "rule", "-p", str(tmp_path), "--with-content", "-o", "json"],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    assert "content" in parsed["knowledge"][0]


def test_types_filter_with_from_spec(tmp_path: Path) -> None:
    _seed_ai_memory(tmp_path)
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "rules" / "rule-a.yml",
        {"knowledge_id": "rule-a", "title": "coupon"},
    )
    _write_yml(
        tmp_path / ".ai-memory" / "knowledge" / "pitfalls" / "pit-a.yml",
        {"knowledge_id": "pit-a", "title": "coupon", "symptom": "fails"},
    )
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("# 优惠券需求", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        _make_app(),
        [
            "recall",
            "--from-spec",
            str(spec_path),
            "-p",
            str(tmp_path),
            "-t",
            "pitfalls",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    parsed = json.loads(result.stdout)
    cats = {k["category"] for k in parsed["knowledge"]}
    assert cats <= {"pitfalls"}
