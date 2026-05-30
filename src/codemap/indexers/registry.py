"""Indexer registry — combines built-in and entry_points-registered indexers.

Discovery rule (ADR-004): all indexers — whether they live in this repository
or in a third-party plugin package — are loaded via the ``codemap.indexers``
entry-point group. There is no "built-in" privilege.
"""

from __future__ import annotations

import importlib.metadata
import logging
from collections.abc import Iterator
from pathlib import Path
from threading import Lock

from codemap.indexers.base import Indexer

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "codemap.indexers"


class IndexerRegistry:
    """Holds discovered indexer instances. Discovery is lazy + cached."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._by_name: dict[str, Indexer] | None = None

    # ------------------------------------------------------------- discovery

    def reload(self) -> None:
        """Drop the cache; next access re-runs discovery."""
        with self._lock:
            self._by_name = None

    def all(self) -> dict[str, Indexer]:
        """Return discovered indexers keyed by ``Indexer.name``."""
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            return dict(self._by_name)

    def register(self, indexer: Indexer) -> None:
        """Add an indexer manually (mainly for tests / dynamic plugins)."""
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            self._by_name[indexer.name] = indexer

    # --------------------------------------------------------------- lookup

    def for_path(self, path: Path) -> Iterator[Indexer]:
        """Yield indexers that claim ``path`` (via ``supports``)."""
        for ix in self.all().values():
            try:
                if ix.supports(path):
                    yield ix
            except Exception:  # pragma: no cover - defensive
                logger.exception("indexer %r raised in supports()", ix.name)

    # --------------------------------------------------------------- internals

    @staticmethod
    def _discover() -> dict[str, Indexer]:
        out: dict[str, Indexer] = {}
        eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
        for ep in eps:
            try:
                cls = ep.load()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to load indexer entry-point %s", ep.name)
                continue
            try:
                instance = cls()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to instantiate %s from %s", ep.name, ep.value)
                continue
            if not isinstance(instance, Indexer):  # runtime_checkable check
                logger.warning(
                    "entry-point %s -> %s does not satisfy Indexer protocol; skipping",
                    ep.name,
                    ep.value,
                )
                continue
            if instance.name in out:
                logger.warning(
                    "duplicate indexer name %r (entry-point %s overrides previous registration)",
                    instance.name,
                    ep.name,
                )
            out[instance.name] = instance
        return out


_default = IndexerRegistry()


def get_registry() -> IndexerRegistry:
    """Return the process-wide default registry."""
    return _default


__all__ = ["IndexerRegistry", "get_registry"]
