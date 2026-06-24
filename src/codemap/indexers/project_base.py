"""Project-level indexer protocol — runs once over the whole project.

Unlike the per-file :class:`codemap.indexers.base.Indexer` (``index_file``), a
``ProjectIndexer`` consumes the entire project in one pass. Required for
semantic engines (e.g. scip-java) whose output is whole-project, not
single-file. Registered via the ``codemap.project_indexers`` entry-point group
on equal standing with per-file indexers (ADR-004, ADR-L001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from codemap.core.models import IndexResult

__all__ = ["ProjectIndexContext", "ProjectIndexer"]


@dataclass(frozen=True, slots=True)
class ProjectIndexContext:
    project_root: Path
    config: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class ProjectIndexer(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]

    def index_project(self, ctx: ProjectIndexContext) -> IndexResult: ...
