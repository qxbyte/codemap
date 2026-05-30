"""Configuration schema and loader for `.codemap/config.yaml`."""

from __future__ import annotations

from codemap.config.loader import (
    ConfigError,
    dump_config,
    load_config,
    project_config_path,
    user_config_path,
)
from codemap.config.schema import (
    BridgesConfig,
    Config,
    IndexConfig,
    IndexersConfig,
    StorageConfig,
)

__all__ = [
    "BridgesConfig",
    "Config",
    "ConfigError",
    "IndexConfig",
    "IndexersConfig",
    "StorageConfig",
    "dump_config",
    "load_config",
    "project_config_path",
    "user_config_path",
]
