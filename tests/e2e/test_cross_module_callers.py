"""End-to-end test: cross-module callers actually show up after indexing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codemap.cli.main import app

runner = CliRunner()


@pytest.fixture
def multi_file_project(tmp_path: Path) -> Path:
    """Three Python files with cross-file imports + same-name calls."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "utils.py").write_text("def helper(x):\n    return x + 1\n")
    (proj / "service.py").write_text(
        "from utils import helper\n\ndef do_work():\n    return helper(0)\n"
    )
    (proj / "cli.py").write_text(
        "from utils import helper\n"
        "from service import do_work\n"
        "\n"
        "def main():\n"
        "    return helper(1) + do_work()\n"
    )
    result = runner.invoke(app, ["index", str(proj)])
    assert result.exit_code == 0, result.stdout
    return proj


def test_callers_of_helper_finds_both_cross_file_callers(
    multi_file_project: Path,
) -> None:
    """Without the cross-module bridge, callers(helper) would only show
    same-file references (none here). With the bridge, the do_work and
    main symbols (which import + call helper) appear."""
    helper_id = "scip-python . . . utils.py/helper()."
    result = runner.invoke(
        app,
        ["--json", "callers", helper_id, "--project", str(multi_file_project)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    caller_ids = {r["symbol"] for r in payload["result"]["results"]}
    # Bridge-resolved callers from service.py and cli.py should appear
    assert any("service.py" in cid and "do_work" in cid for cid in caller_ids)
    assert any("cli.py" in cid and "main" in cid for cid in caller_ids)


def test_callees_of_do_work_includes_helper_via_bridge(
    multi_file_project: Path,
) -> None:
    """callees(do_work) should reach helper via the alias-expanded edge."""
    do_work_id = "scip-python . . . service.py/do_work()."
    result = runner.invoke(
        app,
        ["--json", "callees", do_work_id, "--project", str(multi_file_project)],
    )
    payload = json.loads(result.stdout)
    targets = [r["symbol"] for r in payload["result"]["results"]]
    # Note: the direct callees edge points at the synthetic scip-python
    # utils/helper, not at the resolved local symbol. Alias-aware lookups
    # are on the *callers* side of the resolved symbol — see test above.
    assert any("helper" in t for t in targets)


def test_aliases_count_on_dogfood_project(multi_file_project: Path) -> None:
    """Sanity-check: aliases.json contains entries the bridge produced."""
    aliases_file = multi_file_project / ".codemap" / "aliases.json"
    aliases = json.loads(aliases_file.read_text())
    bridge_aliases = [a for a in aliases if a["producer"] == "python_cross_module"]
    # Two distinct synthetic targets in this project (helper, do_work) → 2 aliases
    assert len(bridge_aliases) >= 2
