"""Bridge registry with topological resolution.

Mirrors :class:`codemap.indexers.registry.IndexerRegistry`: entry-point-based
discovery, no built-in privilege. Adds a :meth:`topological_order` helper so
the orchestrator can run bridges in dependency order.
"""

from __future__ import annotations

import importlib.metadata
import logging
from threading import Lock

from codemap.core.bridge.base import Bridge

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "codemap.bridges"


class BridgeCycleError(RuntimeError):
    """Raised when bridge ``requires`` declarations contain a cycle."""


class BridgeRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_name: dict[str, Bridge] | None = None

    def reload(self) -> None:
        with self._lock:
            self._by_name = None

    def all(self) -> dict[str, Bridge]:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            return dict(self._by_name)

    def register(self, bridge: Bridge) -> None:
        with self._lock:
            if self._by_name is None:
                self._by_name = self._discover()
            self._by_name[bridge.name] = bridge

    def topological_order(self) -> list[Bridge]:
        """Return bridges in an order satisfying their ``requires`` declarations."""
        bridges = self.all()
        in_degree: dict[str, int] = {name: 0 for name in bridges}
        forward: dict[str, list[str]] = {name: [] for name in bridges}
        for name, b in bridges.items():
            for dep in b.requires:
                if dep not in bridges:
                    logger.warning(
                        "bridge %r requires %r which is not registered; ignoring",
                        name,
                        dep,
                    )
                    continue
                in_degree[name] += 1
                forward[dep].append(name)

        ready = [n for n, d in in_degree.items() if d == 0]
        order: list[Bridge] = []
        while ready:
            ready.sort()  # deterministic order for reproducibility
            current = ready.pop(0)
            order.append(bridges[current])
            for downstream in forward[current]:
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    ready.append(downstream)
        if len(order) != len(bridges):
            unresolved = [n for n, d in in_degree.items() if d > 0]
            raise BridgeCycleError(f"bridge dependency cycle among: {sorted(unresolved)}")
        return order

    @staticmethod
    def _discover() -> dict[str, Bridge]:
        out: dict[str, Bridge] = {}
        eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
        for ep in eps:
            try:
                cls = ep.load()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to load bridge entry-point %s", ep.name)
                continue
            try:
                instance = cls()
            except Exception:  # pragma: no cover - bad plugin
                logger.exception("failed to instantiate bridge %s", ep.name)
                continue
            if not isinstance(instance, Bridge):
                logger.warning(
                    "entry-point %s -> %s does not satisfy Bridge protocol; skipping",
                    ep.name,
                    ep.value,
                )
                continue
            if instance.name in out:
                logger.warning(
                    "duplicate bridge name %r (entry-point %s overrides previous)",
                    instance.name,
                    ep.name,
                )
            out[instance.name] = instance
        return out


_default = BridgeRegistry()


def get_registry() -> BridgeRegistry:
    return _default


__all__ = ["BridgeCycleError", "BridgeRegistry", "get_registry"]
