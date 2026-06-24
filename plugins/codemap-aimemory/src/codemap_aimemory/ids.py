"""Derive stable, unique ``entity_id`` slugs from SCIP symbol id strings.

Rules:

* base slug = ``{prefix}-{last_descriptor_name}`` where ``prefix`` is
  decided by the symbol's kind via :func:`prefix_for` (fn / cls / tbl /
  route / field / sym).
* if multiple symbols collide on the same base slug (different SCIP ids
  but same kind + last name), every entry in the collision group gets an
  ``-<sha1[:8]>`` suffix derived from its SCIP id — never just the second
  one, so the resulting ids stay stable when adding / removing symbols.
* iteration order is sorted(symbol_ids) for determinism.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from codemap.core.symbol import SymbolID

__all__ = ["build_entity_ids", "prefix_for", "slug_base"]

_PREFIX_BY_KIND: dict[str, str] = {
    "method": "fn",
    "function": "fn",
    "class": "cls",
    "interface": "cls",
    "table": "tbl",
    "route": "route",
    "field": "field",
    "sql_mapping": "sql",
}


def prefix_for(kind: str) -> str:
    return _PREFIX_BY_KIND.get(kind, "sym")


def slug_base(symbol_id_str: str) -> str:
    return SymbolID.parse(symbol_id_str).descriptors[-1].name


def build_entity_ids(
    symbol_ids: list[str],
    kinds: dict[str, str] | None = None,
) -> dict[str, str]:
    kinds = kinds or {}
    base_of: dict[str, str] = {}
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for sid in sorted(symbol_ids):
        base = f"{prefix_for(kinds.get(sid, ''))}-{slug_base(sid)}"
        base_of[sid] = base
        groups[base].append(sid)
    out: dict[str, str] = {}
    for sid in symbol_ids:
        base = base_of[sid]
        if len(groups[base]) == 1:
            out[sid] = base
        else:
            h = hashlib.sha1(sid.encode("utf-8")).hexdigest()[:8]
            out[sid] = f"{base}-{h}"
    return out
