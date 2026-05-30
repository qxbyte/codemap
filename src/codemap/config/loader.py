"""Load and merge `.codemap/config.yaml` from defaults / user / project."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from codemap.config.schema import Config

PROJECT_CONFIG_FILENAME = "config.yaml"


class ConfigError(ValueError):
    """Raised when a config file is malformed or fails schema validation."""


def user_config_path() -> Path:
    """Return ``~/.config/codemap/config.yaml`` regardless of whether it exists."""
    return Path.home() / ".config" / "codemap" / PROJECT_CONFIG_FILENAME


def project_config_path(codemap_dir: Path) -> Path:
    return codemap_dir / PROJECT_CONFIG_FILENAME


def load_config(codemap_dir: Path | None = None) -> Config:
    """Load defaults → user-level → project-level config, merged in that order.

    ``codemap_dir`` is the ``.codemap/`` directory; the project-level file
    lives there. Pass ``None`` to skip the project layer (useful for CLI
    invocations against an unindexed directory).

    Raises :class:`ConfigError` on parse or validation failure. Missing
    files are not errors — they leave the layer at defaults.
    """
    merged: dict[str, Any] = {}
    _merge_into(merged, _read_yaml(user_config_path()))
    if codemap_dir is not None:
        _merge_into(merged, _read_yaml(project_config_path(codemap_dir)))
    try:
        return Config.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(
            "config validation failed:\n"
            + "\n".join(
                f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
            )
        ) from exc


def _read_yaml(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"failed to parse {path}: {exc}") from exc
    if raw is None:  # empty file
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{path} must contain a YAML mapping at the root")
    return cast("Mapping[str, Any]", raw)


def _merge_into(dst: dict[str, Any], src: Mapping[str, Any]) -> None:
    """Recursive dict merge: nested mappings are merged key-by-key, scalars
    and lists in ``src`` replace whatever ``dst`` holds.
    """
    for key, value in src.items():
        existing = dst.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            _merge_into(existing, value)
        else:
            dst[key] = value


def dump_config(config: Config) -> str:
    """Render a Config back into YAML for ``codemap config show``."""
    return yaml.safe_dump(
        config.model_dump(mode="json"),
        sort_keys=False,
        default_flow_style=False,
    )


__all__ = [
    "ConfigError",
    "dump_config",
    "load_config",
    "project_config_path",
    "user_config_path",
]
