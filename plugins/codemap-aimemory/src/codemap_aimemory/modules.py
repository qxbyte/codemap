"""Per-file module aggregator — backs ``entities/modules.yml``.

P1-1 follow-up: codemap already emits per-symbol entities (``fn-*``,
``cls-*``). The four-layer memory model docs (§7) also ask for a coarser
``modules/`` view that groups symbols by the file/package that owns them,
so an Agent can ask "what lives in the order pricing module?" without
walking every function entity.

This module is pure: ``aggregate_modules(symbols, entity_ids)`` returns a
list of dicts ready for YAML dump. Persistence lives in
:class:`codemap_aimemory.emitter.AiMemoryEmitter`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

__all__ = ["aggregate_modules", "file_to_module_slug"]

_FN_KINDS = frozenset({"method", "function"})
_CLS_KINDS = frozenset({"class", "interface"})

_STRIPPABLE_PREFIXES = ("src/main/java/", "src/main/", "src/", "lib/", "app/")


def aggregate_modules(
    symbols: Iterable[Any],
    entity_ids: dict[str, str],
) -> list[dict[str, Any]]:
    """Group functions and classes by their owning ``file``.

    Files that contain only non-fn/cls symbols (e.g. ``table`` rows in an
    XML mapper) are intentionally omitted — they're already covered by
    ``entities/tables.yml`` / ``entities/files.yml``.
    """
    by_file: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"functions": [], "classes": []})
    language_by_file: dict[str, str] = {}

    for sym in symbols:
        sid = str(sym.id)
        eid = entity_ids.get(sid)
        if not eid:
            continue
        file_key = str(sym.file)  # store hands back PurePosixPath
        if sym.kind in _FN_KINDS:
            by_file[file_key]["functions"].append(eid)
        elif sym.kind in _CLS_KINDS:
            by_file[file_key]["classes"].append(eid)
        else:
            continue
        # capture language on first occurrence; subsequent symbols in the
        # same file are expected to match.
        language_by_file.setdefault(file_key, getattr(sym, "language", "") or "")

    modules: list[dict[str, Any]] = []
    for file in sorted(by_file):
        content = by_file[file]
        slug = file_to_module_slug(file)
        modules.append(
            {
                "id": f"mod-{slug}",
                "type": "module",
                "path": str(file),
                "language": language_by_file.get(file, ""),
                "fn_count": len(content["functions"]),
                "cls_count": len(content["classes"]),
                "functions": sorted(content["functions"]),
                "classes": sorted(content["classes"]),
            }
        )
    return modules


def file_to_module_slug(file: str) -> str:
    """Stable, filesystem-safe slug for ``mod-<slug>``.

    Strips common source-root prefixes and the file extension so the slug
    reads like a dotted-ish module path:

    >>> file_to_module_slug("src/codemap/cli/commands/index.py")
    'codemap-cli-commands-index'
    >>> file_to_module_slug("src/main/java/com/demo/Svc.java")
    'com-demo-Svc'
    """
    path = file.replace("\\", "/")
    for prefix in _STRIPPABLE_PREFIXES:
        if path.startswith(prefix):
            path = path[len(prefix) :]
            break
    base = path.rsplit("/", 1)
    dir_part = base[0] if len(base) == 2 else ""
    name_part = base[-1]
    if "." in name_part:
        name_part = name_part.rsplit(".", 1)[0]
    rebuilt = f"{dir_part}/{name_part}" if dir_part else name_part
    return rebuilt.replace("/", "-").replace(".", "-")
