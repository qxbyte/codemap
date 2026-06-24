"""Registry for emitters (group ``codemap.emitters``).

Mirrors the indexer / project-indexer registries: lazy, cached, thread-safe
entry-point discovery; ``runtime_checkable`` Protocol filter rejects entries
that don't satisfy :class:`Emitter`.
"""

from __future__ import annotations

import importlib.metadata
import logging
from threading import Lock

from codemap.emitters.base import Emitter

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "codemap.emitters"


class EmitterRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_name: dict[str, Emitter] | None = None

    def reload(self) -> None:
        with self._lock:
            self._by_name = None

    def all(self) -> dict[str, Emitter]:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            return dict(self._by_name)

    def register(self, emitter: Emitter) -> None:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            self._by_name[emitter.name] = emitter

    @staticmethod
    def _discover() -> dict[str, Emitter]:
        out: dict[str, Emitter] = {}
        for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP):
            try:
                cls = ep.load()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to load emitter entry-point %s", ep.name)
                continue
            try:
                instance = cls()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to instantiate %s from %s", ep.name, ep.value)
                continue
            if not isinstance(instance, Emitter):
                logger.warning(
                    "entry-point %s -> %s does not satisfy Emitter; skipping",
                    ep.name,
                    ep.value,
                )
                continue
            if instance.name in out:
                logger.warning(
                    "duplicate emitter name %r (entry-point %s overrides previous)",
                    instance.name,
                    ep.name,
                )
            out[instance.name] = instance
        return out


_default = EmitterRegistry()


def get_emitter_registry() -> EmitterRegistry:
    return _default


__all__ = ["EmitterRegistry", "get_emitter_registry"]
