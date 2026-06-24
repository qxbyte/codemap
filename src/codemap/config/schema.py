"""Configuration schema for `.codemap/config.yaml`.

Pydantic models double as the single source of truth: the YAML loader
validates against them, the CLI renders them, the in-memory ``Config``
object is what callers ever touch. ``extra="forbid"`` ensures typos and
deprecated keys surface as errors rather than silently being ignored.

Layered loading (cf. ``codemap.config.loader.load_config``):

1. Built-in defaults — every field has a sensible value.
2. User-level file at ``~/.config/codemap/config.yaml`` (overrides defaults).
3. Project-level file at ``<project>/.codemap/config.yaml`` (overrides user).
4. CLI flags (overrides everything; not handled here).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 10 MB. Matches the previous hard-coded value in `codemap.cli.commands.index`.
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024

# Directories ignored even when not explicitly listed in the config — they
# are universally noise and would otherwise dominate the index.
DEFAULT_PRUNE_DIRS: tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    ".codemap",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",  # Maven build output
    "out",  # Gradle build output (IDE default)
)


class _Base(BaseModel):
    """Common pydantic config for every config section."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        validate_assignment=True,
    )


class StorageConfig(_Base):
    """Persistence backend configuration."""

    backend: Literal["json", "sqlite"] = "json"


class IndexConfig(_Base):
    """File-discovery and parsing limits."""

    ignore: list[str] = Field(default_factory=list)
    """Extra glob patterns to exclude during indexing.

    Patterns are matched with ``fnmatch.fnmatch`` against the project-
    relative POSIX path of each candidate file *and* against each directory
    name during ``os.walk``. Use ``**/dist/**`` for path-anchored
    exclusions and ``*.bak`` for filename matching.
    """

    max_file_bytes: int = Field(default=DEFAULT_MAX_FILE_BYTES, ge=1)
    """Files larger than this byte count are skipped with a diagnostic."""

    follow_symlinks: bool = False
    """If ``True``, ``os.walk`` follows symlinks. Use cautiously — cycles
    are guarded by inode tracking but can still slow indexing significantly."""


class IndexersConfig(_Base):
    """Which indexer plugins to actually run."""

    enabled: list[str] | Literal["all"] = "all"
    """Either ``"all"`` (default) or an explicit list of indexer names.

    A name in this list that does not match any registered indexer is
    silently ignored — third-party plugins may come and go between
    workstations and we don't want to break indexing on a stale config.
    """

    disabled: list[str] = Field(default_factory=list)
    """Indexer names to skip even when ``enabled = "all"``.

    The ``_example_lang`` reference indexer is a typical entry here once
    real indexers are in play."""


class BridgesConfig(_Base):
    """Which bridge plugins to actually run."""

    enabled: list[str] | Literal["all"] = "all"
    disabled: list[str] = Field(default_factory=list)


class Config(_Base):
    """Top-level CodeMap configuration."""

    storage: StorageConfig = Field(default_factory=StorageConfig)
    index: IndexConfig = Field(default_factory=IndexConfig)
    indexers: IndexersConfig = Field(default_factory=IndexersConfig)
    bridges: BridgesConfig = Field(default_factory=BridgesConfig)


__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_PRUNE_DIRS",
    "BridgesConfig",
    "Config",
    "IndexConfig",
    "IndexersConfig",
    "StorageConfig",
]
