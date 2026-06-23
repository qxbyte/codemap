"""Registry for project-level indexers (group ``codemap.project_indexers``).

Mirrors :class:`codemap.indexers.registry.IndexerRegistry` for the project-
level variant. Discovery is lazy, cached, and thread-safe; the same
``runtime_checkable`` protocol filter rejects entries that don't satisfy
:class:`ProjectIndexer`.
"""

from __future__ import annotations

import importlib.metadata
import logging
from threading import Lock

from codemap.indexers.project_base import ProjectIndexer

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "codemap.project_indexers"


class ProjectIndexerRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_name: dict[str, ProjectIndexer] | None = None

    def reload(self) -> None:
        with self._lock:
            self._by_name = None

    def all(self) -> dict[str, ProjectIndexer]:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            return dict(self._by_name)

    def register(self, indexer: ProjectIndexer) -> None:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            self._by_name[indexer.name] = indexer

    @staticmethod
    def _discover() -> dict[str, ProjectIndexer]:
        out: dict[str, ProjectIndexer] = {}
        for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP):
            try:
                cls = ep.load()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to load project indexer entry-point %s", ep.name)
                continue
            try:
                instance = cls()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to instantiate %s from %s", ep.name, ep.value)
                continue
            if not isinstance(instance, ProjectIndexer):
                logger.warning(
                    "entry-point %s -> %s does not satisfy ProjectIndexer; skipping",
                    ep.name,
                    ep.value,
                )
                continue
            if instance.name in out:
                logger.warning(
                    "duplicate project indexer name %r (entry-point %s overrides previous)",
                    instance.name,
                    ep.name,
                )
            out[instance.name] = instance
        return out


_default = ProjectIndexerRegistry()


def get_project_registry() -> ProjectIndexerRegistry:
    return _default


__all__ = ["ProjectIndexerRegistry", "get_project_registry"]
