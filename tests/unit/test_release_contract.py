from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).parents[2]
CORE_VERSION = "0.4.10"
SEMANTIC_VERSION = "0.2.3"


def _project(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return cast("dict[str, Any]", tomllib.load(stream)["project"])


def _package_projects() -> list[tuple[str, Path, dict[str, Any]]]:
    paths = [ROOT / "pyproject.toml", *sorted((ROOT / "plugins").glob("*/pyproject.toml"))]
    return [(str(project["name"]), path, project) for path in paths if (project := _project(path))]


def _workflow_packages(workflow_name: str, job_name: str) -> set[tuple[str, str]]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / workflow_name).read_text())
    rows = workflow["jobs"][job_name]["strategy"]["matrix"]["package"]
    return {(row["name"], row["dir"]) for row in rows}


def _test_workflow_local_dependencies() -> dict[str, str]:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())
    rows = workflow["jobs"]["package"]["strategy"]["matrix"]["package"]
    return {row["name"]: row["local_deps"] for row in rows if "local_deps" in row}


def test_distribution_names_are_unique() -> None:
    names = [name for name, _path, _project_data in _package_projects()]

    assert len(names) == 21
    assert len(names) == len(set(names))


def test_publish_matrix_matches_repository_packages() -> None:
    expected = {
        (name, "." if path == ROOT / "pyproject.toml" else str(path.parent.relative_to(ROOT)))
        for name, path, _project_data in _package_projects()
    }

    assert _workflow_packages("publish.yml", "publish") == expected


def test_test_workflow_preflights_publish_matrix() -> None:
    assert _workflow_packages("test.yml", "package") == _workflow_packages("publish.yml", "publish")


def test_test_workflow_installs_unpublished_local_plugin_dependencies() -> None:
    assert _test_workflow_local_dependencies() == {
        "codemap-mybatis": "plugins/codemap-java",
        "codemap-semantic-index": "plugins/codemap-aimemory",
    }


def test_release_uses_expected_version_groups() -> None:
    actual = {name: project["version"] for name, _path, project in _package_projects()}
    expected = {
        name: SEMANTIC_VERSION if name == "codemap-semantic-index" else CORE_VERSION
        for name in actual
    }

    assert actual == expected


def test_every_plugin_accepts_release_core_version() -> None:
    release_core = Version(CORE_VERSION)

    for name, _path, project in _package_projects():
        if name == "codemap-core":
            continue
        core_requirements = [
            Requirement(raw)
            for raw in project.get("dependencies", [])
            if canonicalize_name(Requirement(raw).name) == "codemap-core"
        ]
        assert len(core_requirements) == 1, name
        assert release_core in core_requirements[0].specifier, name
