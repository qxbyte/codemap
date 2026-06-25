"""Tests for the L0 ``project.yml`` builder (P0-3).

The four-layer memory model lays L0 (project meta) alongside the existing
L1 entities/relations under ``.ai-memory/``. This module covers the pure
collector ``build_project_meta(project_root)`` — its emitter wiring is
tested in ``test_emitter.py``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from codemap_aimemory.project_meta import build_project_meta

# ---------- pure collection ----------


def test_python_project_detected_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        'dependencies = ["typer>=0.12", "pydantic>=2.0"]\n'
        "\n[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0", "ruff"]\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "src" / "b.py").write_text("y = 2\n")

    meta = build_project_meta(tmp_path)

    assert meta["schema_version"] == "1.0"
    assert meta["root"] == str(tmp_path)
    assert meta["tech_stack"]["primary_language"] == "python"
    assert "pyproject.toml" in meta["tech_stack"]["manifests"]
    assert "typer>=0.12" in meta["dependencies"]["runtime"]
    assert "pytest>=8.0" in meta["dependencies"]["dev"]


def test_node_project_detected_from_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "dependencies": {"vue": "^3.4.0", "axios": "^1.6.0"},
                "devDependencies": {"vite": "^5.0.0"},
            }
        )
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.vue").write_text("<template></template>")
    (tmp_path / "src" / "main.ts").write_text("export const x = 1;")

    meta = build_project_meta(tmp_path)

    assert meta["tech_stack"]["primary_language"] in {"vue", "typescript"}
    assert "package.json" in meta["tech_stack"]["manifests"]
    assert "vue@^3.4.0" in meta["dependencies"]["runtime"]
    assert "vite@^5.0.0" in meta["dependencies"]["dev"]


def test_java_maven_project_detected(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text(
        '<?xml version="1.0"?>\n'
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <groupId>com.demo</groupId>\n"
        "  <artifactId>demo</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</project>\n"
    )
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "src" / "main" / "java" / "Hello.java").write_text("class Hello {}")

    meta = build_project_meta(tmp_path)

    assert meta["tech_stack"]["primary_language"] == "java"
    assert "pom.xml" in meta["tech_stack"]["manifests"]


def test_top_dirs_collected_one_level_only(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src" / "deep").mkdir()  # should NOT appear

    meta = build_project_meta(tmp_path)

    top = set(meta["top_dirs"])
    assert {"src", "tests", "docs"} <= top
    # hidden + dependency dirs filtered
    assert ".git" not in top
    assert ".venv" not in top
    assert "node_modules" not in top
    assert "deep" not in top


def test_configs_lists_key_files(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    (tmp_path / "Makefile").write_text("all:\n\techo hi\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci")

    meta = build_project_meta(tmp_path)

    configs = set(meta["configs"])
    assert "pyproject.toml" in configs
    assert "Dockerfile" in configs
    assert "Makefile" in configs
    assert ".github/workflows/ci.yml" in configs


def test_git_metadata_extracted_when_repo_present(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/u/r.git"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )

    meta = build_project_meta(tmp_path)

    assert meta["git"]["remote"] == "https://example.com/u/r.git"
    assert meta["git"]["branch"] == "main"
    assert len(meta["git"]["head"]) == 40  # full sha


def test_git_block_empty_when_not_a_repo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    meta = build_project_meta(tmp_path)
    assert meta["git"] == {}


def test_git_resolves_head_via_packed_refs(tmp_path: Path) -> None:
    """``git gc`` packs loose refs; the loose file under refs/heads/ is gone
    and ``packed-refs`` carries the sha. Reader must follow that fallback."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "x.txt").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "pack-refs", "--all"], cwd=tmp_path, check=True)
    loose = tmp_path / ".git" / "refs" / "heads" / "main"
    assert not loose.exists(), "pack-refs should have removed the loose ref"

    meta = build_project_meta(tmp_path)

    assert meta["git"]["branch"] == "main"
    assert len(meta["git"]["head"]) == 40


def test_git_detached_head_records_sha_without_branch(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "x.txt").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "--detach", head], cwd=tmp_path, check=True)

    meta = build_project_meta(tmp_path)

    assert meta["git"]["head"] == head
    assert "branch" not in meta["git"]


def test_git_uses_zero_subprocesses_in_normal_repo(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Performance guard: emitter runs on every ``codemap index``; spawning
    three ``git`` subprocesses here costs ~30 ms each — the 0.3.2 bench
    regression that prompted this rewrite. Worktrees still fall back to
    subprocess."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "x.txt").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )

    from codemap_aimemory import project_meta as pm

    calls: list[list[str]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(args[0]))
        raise AssertionError("subprocess should not be invoked for normal git repos")

    monkeypatch.setattr(pm.subprocess, "run", fake_run)

    meta = build_project_meta(tmp_path)
    assert meta["git"]["branch"] == "main"
    assert calls == []


def test_language_breakdown_counts_known_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1")
    (tmp_path / "b.py").write_text("y=2")
    (tmp_path / "c.java").write_text("class C{}")
    (tmp_path / "d.md").write_text("# doc")
    meta = build_project_meta(tmp_path)
    langs = meta["languages"]
    assert langs.get("python") == 2
    assert langs.get("java") == 1
    assert langs.get("markdown") == 1


def test_no_manifest_fallback_to_file_counts(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1")
    (tmp_path / "b.py").write_text("y=2")
    meta = build_project_meta(tmp_path)
    assert meta["tech_stack"]["primary_language"] == "python"
    assert meta["tech_stack"]["manifests"] == []


def test_generated_at_is_iso_date(tmp_path: Path) -> None:
    meta = build_project_meta(tmp_path)
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", meta["generated_at"])


# ---------- ignored dirs do not pollute scans ----------


def test_language_scan_skips_venv_and_node_modules(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x=1")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "junk.py").write_text("# huge venv file")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("//")
    meta = build_project_meta(tmp_path)
    # only the src/a.py should be counted
    assert meta["languages"].get("python") == 1
    assert "javascript" not in meta["languages"]
