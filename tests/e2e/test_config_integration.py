"""End-to-end: `.codemap/config.yaml` actually shapes `codemap index`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app
from codemap.diagnostics.exit_codes import ExitCode

runner = CliRunner()


@pytest.fixture
def fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect ``Path.home()`` so user-level config doesn't bleed in."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def _seed_project(
    project: Path,
    files: dict[str, str],
    config_yaml: str | None = None,
) -> None:
    for rel, body in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    if config_yaml is not None:
        cmdir = project / ".codemap"
        cmdir.mkdir(parents=True, exist_ok=True)
        (cmdir / "config.yaml").write_text(config_yaml)


# ---------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------


def test_config_show_default(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    result = runner.invoke(app, ["--json", "config", "show", "--project", str(project)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    cfg = payload["result"]["config"]
    assert cfg["storage"]["backend"] == "json"
    assert cfg["indexers"]["enabled"] == "all"


def test_config_show_picks_up_project_file(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {},
        "indexers:\n  disabled: ['_example_lang']\n",
    )
    result = runner.invoke(app, ["--json", "config", "show", "--project", str(project)])
    cfg = json.loads(result.stdout)["result"]["config"]
    assert cfg["indexers"]["disabled"] == ["_example_lang"]


def test_config_show_friendly_error_on_invalid_yaml(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(project, {}, "storage:\n  backend: redis\n")
    result = runner.invoke(app, ["config", "show", "--project", str(project)])
    assert result.exit_code == int(ExitCode.CONFIG_ERROR)
    assert "storage.backend" in result.output


# ---------------------------------------------------------------------------
# Index respects config
# ---------------------------------------------------------------------------


def test_index_ignore_pattern_skips_files(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {
            "keep.py": "def kept(): pass\n",
            "skip.py": "def skipped(): pass\n",
        },
        "index:\n  ignore: ['skip.py']\n",
    )
    result = runner.invoke(app, ["--json", "index", str(project)])
    assert result.exit_code == 0
    res = json.loads(result.stdout)["result"]
    assert res["files_indexed"] == 1


def test_index_ignore_directory_glob(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {
            "src/a.py": "def a(): pass\n",
            "vendor/lib.py": "def vendored(): pass\n",
        },
        "index:\n  ignore: ['vendor']\n",
    )
    result = runner.invoke(app, ["--json", "index", str(project)])
    res = json.loads(result.stdout)["result"]
    assert res["files_indexed"] == 1


def test_index_disabled_indexer_is_not_run(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {
            "real.py": "def f(): pass\n",
            "demo.example": "def x\n",
        },
        "indexers:\n  disabled: ['_example_lang']\n",
    )
    result = runner.invoke(app, ["--json", "index", str(project)])
    res = json.loads(result.stdout)["result"]
    # Only real.py contributes; demo.example is ignored entirely.
    assert res["files_indexed"] == 1
    assert res["symbols"] >= 1


def test_index_indexers_enabled_explicit_list(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {
            "real.py": "def f(): pass\n",
            "demo.example": "def x\n",
        },
        "indexers:\n  enabled: ['python']\n",
    )
    result = runner.invoke(app, ["--json", "index", str(project)])
    res = json.loads(result.stdout)["result"]
    assert res["files_indexed"] == 1


def test_index_bridges_disabled_no_routes(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {
            "server.py": ("app = object()\n@app.get('/api/x')\ndef h(): pass\n"),
        },
        "bridges:\n  disabled: ['http_route']\n",
    )
    runner.invoke(app, ["index", str(project)])
    result = runner.invoke(app, ["--json", "routes", "--project", str(project)])
    payload = json.loads(result.stdout)
    assert payload["result"]["results"] == []


def test_index_max_file_bytes_skips_large_file(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    big = "def f(): pass\n" + "# pad\n" * 200
    _seed_project(
        project,
        {"big.py": big},
        f"index:\n  max_file_bytes: {len(big) - 50}\n",
    )
    result = runner.invoke(app, ["--json", "index", str(project)])
    res = json.loads(result.stdout)["result"]
    assert res["files_indexed"] == 0


# ---------------------------------------------------------------------------
# Error path: invalid config blocks the index
# ---------------------------------------------------------------------------


def test_index_with_invalid_config_exits_config_error(fake_home: Path, tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _seed_project(
        project,
        {"a.py": "def a(): pass\n"},
        "storage:\n  backend: redis\n",
    )
    result = runner.invoke(app, ["index", str(project)])
    assert result.exit_code == int(ExitCode.CONFIG_ERROR)
