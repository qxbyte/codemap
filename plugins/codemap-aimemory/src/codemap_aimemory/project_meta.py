"""L0 project metadata collector — feeds ``.ai-memory/project.yml``.

The four-layer memory model puts a thin "what project is this" sheet at L0
so downstream Agents (Claude, custom tooling) can answer questions like
"which package manager does this use?" and "what's the git remote?"
without re-discovering it every turn.

This module is pure: a single function ``build_project_meta(root)`` returns
a serialisable dict. Persistence lives in
:class:`codemap_aimemory.emitter.AiMemoryEmitter`.

Detection is best-effort and avoids any heavy parsing — manifests are
parsed for *names* of dependencies only, not version-resolved.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["build_project_meta"]


_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "dist",
        "build",
        "target",
        "out",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".nox",
        ".codemap",
        ".ai-memory",
        ".idea",
        ".vscode",
    }
)


_CODE_EXTS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".vue": "vue",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".sql": "sql",
    ".css": "css",
    ".scss": "css",
    ".html": "html",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
}

_DOC_EXTS: dict[str, str] = {
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".xml": "xml",
}

_EXT_MAP: dict[str, str] = {**_CODE_EXTS, **_DOC_EXTS}


_MANIFEST_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
)


_PRIMARY_FROM_MANIFEST: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "kotlin",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "Gemfile": "ruby",
}


_CONFIG_TOP_LEVEL: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "Gemfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "tox.ini",
    ".gitignore",
)


def build_project_meta(project_root: Path) -> dict[str, Any]:
    """Collect L0 project metadata for ``.ai-memory/project.yml``.

    Returns a JSON/YAML-safe dict; never raises for missing files — absent
    sections are returned as empty dicts/lists. ``git`` is ``{}`` when
    ``project_root`` is not a git checkout.
    """
    manifests = _detect_manifests(project_root)
    languages = _count_languages(project_root)
    primary = _detect_primary_language(manifests, languages)
    deps = _detect_dependencies(project_root, manifests)
    git = _git_meta(project_root)
    top_dirs = _collect_top_dirs(project_root)
    configs = _collect_configs(project_root)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "root": str(project_root),
        "tech_stack": {
            "primary_language": primary,
            "manifests": manifests,
        },
        "languages": languages,
        "dependencies": deps,
        "git": git,
        "top_dirs": top_dirs,
        "configs": configs,
    }


# ---------- manifests / primary language ----------


def _detect_manifests(root: Path) -> list[str]:
    return [name for name in _MANIFEST_FILES if (root / name).is_file()]


def _detect_primary_language(manifests: list[str], languages: dict[str, int]) -> str:
    if "package.json" in manifests:
        if languages.get("vue", 0) > 0:
            return "vue"
        ts = languages.get("typescript", 0)
        js = languages.get("javascript", 0)
        if ts >= js and ts > 0:
            return "typescript"
        if js > 0:
            return "javascript"
        return "javascript"

    for manifest, lang in _PRIMARY_FROM_MANIFEST.items():
        if manifest in manifests:
            return lang

    code_only = {lang: n for ext, lang in _CODE_EXTS.items() for n in [languages.get(lang, 0)] if n}
    if code_only:
        return max(code_only.items(), key=lambda kv: kv[1])[0]
    return "unknown"


# ---------- language file counts ----------


def _count_languages(root: Path) -> dict[str, int]:
    """Walk the tree and tally files by extension.

    Hot path on every ``codemap index``: avoid per-file ``Path()`` construction
    and ``.suffix`` (which itself parses the path) — a quick ``rfind`` is
    several times faster on a 1000-file codebase.
    """
    counts: dict[str, int] = {}
    ext_map = _EXT_MAP  # local alias — fewer global lookups in the loop
    for _, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_ignored_dir(d)]
        for fname in filenames:
            dot = fname.rfind(".")
            if dot <= 0:
                continue
            ext = fname[dot:].lower()
            lang = ext_map.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return counts


def _is_ignored_dir(name: str) -> bool:
    if name in _IGNORED_DIRS:
        return True
    # hidden dirs other than the ones we explicitly whitelist (.github)
    return name.startswith(".") and name not in {".github"}


# ---------- dependencies ----------


def _detect_dependencies(root: Path, manifests: list[str]) -> dict[str, list[str]]:
    runtime: list[str] = []
    dev: list[str] = []

    if "pyproject.toml" in manifests:
        py_runtime, py_dev = _parse_pyproject(root / "pyproject.toml")
        runtime.extend(py_runtime)
        dev.extend(py_dev)

    if "package.json" in manifests:
        node_runtime, node_dev = _parse_package_json(root / "package.json")
        runtime.extend(node_runtime)
        dev.extend(node_dev)

    return {"runtime": runtime, "dev": dev}


def _parse_pyproject(path: Path) -> tuple[list[str], list[str]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return [], []
    project = data.get("project", {}) if isinstance(data, dict) else {}
    runtime = list(project.get("dependencies", []) or [])
    optional = project.get("optional-dependencies", {}) or {}
    dev: list[str] = []
    for group_name, items in optional.items():
        if group_name in {"dev", "test", "tests", "lint", "type"}:
            dev.extend(items)
    return runtime, dev


def _parse_package_json(path: Path) -> tuple[list[str], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    runtime = [f"{k}@{v}" for k, v in (data.get("dependencies") or {}).items()]
    dev = [f"{k}@{v}" for k, v in (data.get("devDependencies") or {}).items()]
    return runtime, dev


# ---------- git ----------


def _git_meta(root: Path) -> dict[str, str]:
    """Extract branch / head / remote without shelling out to git.

    ``codemap index`` runs the emitter on every invocation, so spawning
    three ``git`` subprocesses (~30 ms each on macOS) here adds up. We
    read ``.git/HEAD`` + the referenced ref + ``.git/config`` directly;
    worktrees (``.git`` is a file) and other oddities fall back to
    ``git`` subprocesses where correctness matters more than speed.
    """
    git_dir = root / ".git"
    if not git_dir.exists():
        return {}
    if not git_dir.is_dir():
        # Worktree: .git is a file pointing at the real gitdir. Fall back
        # to subprocess; resolving worktree layout by hand is error-prone.
        return _git_meta_subprocess(root)
    return _git_meta_fs(git_dir)


def _git_meta_fs(git_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}

    head_file = git_dir / "HEAD"
    if head_file.is_file():
        try:
            head_content = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            head_content = ""
        if head_content.startswith("ref: "):
            ref = head_content[5:].strip()
            out["branch"] = ref.rsplit("/", 1)[-1] if "/" in ref else ref
            sha = _resolve_ref(git_dir, ref)
            if sha:
                out["head"] = sha
        elif len(head_content) == 40 and all(c in "0123456789abcdef" for c in head_content):
            out["head"] = head_content  # detached HEAD

    config_file = git_dir / "config"
    if config_file.is_file():
        try:
            remote = _parse_remote_origin_url(config_file.read_text(encoding="utf-8"))
        except OSError:
            remote = ""
        if remote:
            out["remote"] = remote

    return out


def _resolve_ref(git_dir: Path, ref: str) -> str:
    loose = git_dir / ref
    if loose.is_file():
        try:
            return loose.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    packed = git_dir / "packed-refs"
    if packed.is_file():
        try:
            for raw_line in packed.read_text(encoding="utf-8").splitlines():
                line = raw_line.rstrip()
                if not line or line.startswith(("#", "^")):
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
        except OSError:
            return ""
    return ""


def _parse_remote_origin_url(config_text: str) -> str:
    in_origin = False
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_origin = line.replace(" ", "").replace('"', "") == "[remoteorigin]"
            continue
        if in_origin and line.startswith("url"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return ""


def _git_meta_subprocess(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    remote = _git_cmd(root, ["config", "--get", "remote.origin.url"])
    branch = _git_cmd(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = _git_cmd(root, ["rev-parse", "HEAD"])
    if remote:
        out["remote"] = remote
    if branch:
        out["branch"] = branch
    if head:
        out["head"] = head
    return out


def _git_cmd(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# ---------- top dirs / configs ----------


def _collect_top_dirs(root: Path) -> list[str]:
    out: list[str] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return out
    for p in entries:
        if not p.is_dir():
            continue
        if _is_ignored_dir(p.name):
            continue
        out.append(p.name)
    return out


def _collect_configs(root: Path) -> list[str]:
    out: list[str] = [name for name in _CONFIG_TOP_LEVEL if (root / name).is_file()]
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for pattern in ("*.yml", "*.yaml"):
            out.extend(f".github/workflows/{yml.name}" for yml in sorted(workflows.glob(pattern)))
    return out
