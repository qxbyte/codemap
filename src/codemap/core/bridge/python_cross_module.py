"""Cross-module Python call resolver.

The Python indexer emits ``calls`` edges whose target is a synthetic
``scip-python . . . <module-dotted-ns>/<leaf>.`` symbol whenever a name
came in through an ``import`` statement. That synthetic target rarely
matches a real on-disk symbol — the same function defined in
``foo/bar.py`` lives at ``scip-python . . . foo/bar.py/<leaf>().`` (note
the ``.py`` extension and the method/term suffix).

This bridge bridges the two. After all indexers have run it scans the
edge table, finds calls pointing at unresolved scip-python targets, and
maps each one to a concrete local symbol whose **leaf name matches** and
whose **file stem matches the last namespace segment of the synthetic
target**. Matches are emitted as :class:`Alias` entries so query code
(``callers`` / ``callees`` / ``trace``) can transparently expand them.

The matcher is intentionally simple: it ships as a single-language
heuristic, not a type system. It accepts only one of three confidence
levels:

* ``high`` — exactly one candidate whose file stem equals the last
  namespace segment of the synthetic target.
* ``medium`` — exactly one candidate by leaf name alone, when the
  synthetic target has no namespace segments to disambiguate.
* otherwise — drop the edge (no alias produced).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import ClassVar

from codemap.core.models import Alias, BridgeResult, Confidence, Symbol
from codemap.core.store import ReadOnlyStore
from codemap.core.symbol import DescriptorKind, SymbolID

_PYTHON_SCHEME = "scip-python"
_INDEXABLE_KINDS = frozenset({"function", "method", "class", "field", "variable"})


class PythonCrossModuleBridge:
    name: ClassVar[str] = "python_cross_module"
    version: ClassVar[str] = "0.1.0"
    requires: ClassVar[list[str]] = []

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        leaf_to_symbols: dict[str, list[Symbol]] = defaultdict(list)
        for sym in store.iter_symbols():
            if sym.language != "python":
                continue
            if sym.kind not in _INDEXABLE_KINDS:
                continue
            if not sym.id.descriptors:
                continue
            leaf = sym.id.descriptors[-1].name
            leaf_to_symbols[leaf].append(sym)

        aliases: list[Alias] = []
        seen_sources: set[str] = set()
        for edge in store.iter_edges():
            if edge.kind != "calls":
                continue
            target = edge.target
            if target.scheme != _PYTHON_SCHEME:
                continue
            if store.get(target) is not None:
                continue  # already a real local symbol
            target_key = str(target)
            if target_key in seen_sources:
                continue
            resolved = _resolve_one(target, leaf_to_symbols)
            if resolved is None:
                continue
            local, confidence = resolved
            aliases.append(
                Alias(
                    source=target,
                    targets=[local.id],
                    producer=self.name,
                    confidence=confidence,
                )
            )
            seen_sources.add(target_key)
        return BridgeResult(aliases=aliases)


def _resolve_one(
    target: SymbolID,
    leaf_to_symbols: dict[str, list[Symbol]],
) -> tuple[Symbol, Confidence] | None:
    """Return ``(local Symbol, confidence)`` or ``None``."""
    if not target.descriptors:
        return None
    last = target.descriptors[-1]
    # Terms / methods are the shapes the indexer's _module_symbol_id and
    # _external_symbol_id helpers actually produce; only those are worth
    # trying to resolve here.
    if last.kind not in (DescriptorKind.TERM, DescriptorKind.METHOD, DescriptorKind.META):
        return None
    leaf = last.name
    candidates = leaf_to_symbols.get(leaf, [])
    if not candidates:
        return None

    ns_parts = [d.name for d in target.descriptors[:-1] if d.kind is DescriptorKind.NAMESPACE]
    if ns_parts:
        last_ns = ns_parts[-1]
        matching = [c for c in candidates if PurePosixPath(c.file).stem == last_ns]
        if len(matching) == 1:
            return matching[0], "high"
        # If the namespace chain matches but multiple candidates share the
        # file stem, we don't pick one — the index would lie.
        return None
    if len(candidates) == 1:
        return candidates[0], "medium"
    return None


__all__ = ["PythonCrossModuleBridge"]
