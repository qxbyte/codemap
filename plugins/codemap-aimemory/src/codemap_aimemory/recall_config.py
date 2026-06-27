"""Persistent recall configuration — ``~/.config/codemap/recall.yaml``.

Independent of ``llm.yaml`` because it carries no secret (just paths);
written without 0o600.

Stored fields:

* ``shared_roots`` — opt-in cross-project knowledge directories
  (FIX-3d). recall scans them in addition to the local
  ``<project_root>/.ai-memory/knowledge/`` when the caller passes
  ``include_shared=True`` (CLI: ``--include-shared``). Each entry is an
  absolute path to a directory shaped like a project root (i.e. one
  whose ``.ai-memory/knowledge/<cat>/*.yml`` will be scanned).

Project-root isolation stays the default — shared kicks in only on
explicit opt-in, and shared hits are demoted vs local ones (see
:mod:`codemap_aimemory.recall`).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

__all__ = ["RecallConfig", "config_path", "load", "save"]


@dataclass(frozen=True)
class RecallConfig:
    shared_roots: tuple[str, ...] = field(default_factory=tuple)


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "codemap" / "recall.yaml"


def load(path: Path | None = None) -> RecallConfig:
    target = path or config_path()
    if not target.exists():
        return RecallConfig()
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return RecallConfig()
    if not isinstance(data, dict):
        return RecallConfig()
    roots = data.get("shared_roots") or ()
    if not isinstance(roots, list):
        return RecallConfig()
    return RecallConfig(shared_roots=tuple(str(r) for r in roots if isinstance(r, str)))


def save(config: RecallConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if config.shared_roots:
        payload["shared_roots"] = list(config.shared_roots)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload or {}, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return target


_ = asdict  # re-export-style marker; unused here but keeps parity with config.py
