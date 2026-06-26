"""AiMemoryEmitter — write the four-layer memory model's L0+L1 layout atomically.

Reads a :class:`codemap.core.store.ReadOnlyStore` and emits, under
``<output_dir>/.ai-memory/`` (or the explicit ``output_dir`` if it already
ends in ``.ai-memory``):

* ``project.yml``             — L0 project meta (tech stack, deps, git)
* ``entities/functions.yml``  — fn-/cls- entities with calls/called_by/
  related_tables, signature, line_range, change_count_90d, confidence
* ``entities/tables.yml``     — tbl- entities
* ``entities/files.yml``      — file-* entities
* ``entities/modules.yml``    — mod-* per-file aggregates (fn/cls counts + lists)
* ``relations/call-graph.yml``      — calls edges
* ``relations/table-relations.yml`` — accesses_table edges
* ``relations/rule-constraints.yml`` — empty placeholder (L2 owns)
* ``_global/entities.yml``    — cross-walk of code entities + knowledge yml
  references (L1 ↔ L2/L3 lookup; P1-2)

If an ``enrichment/`` folder sits alongside the output, the emitter loads
``business_meaning`` / ``related_rules`` keyed by ``symbol_id`` and merges
them in — but never writes back to the core index. Per ADR-0013 / the
spec's two-layer separation, the deterministic index never carries
explanation text.

All writes are atomic (tmp + ``os.replace``) so an Agent reading
``.ai-memory/`` mid-rebuild never sees a partial tree.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, ClassVar

import yaml

from codemap.core.store import ReadOnlyStore
from codemap.emitters.base import EmitContext, EmitResult
from codemap_aimemory.enrich import load_enrichment
from codemap_aimemory.global_entities import build_global_entities
from codemap_aimemory.ids import build_entity_ids
from codemap_aimemory.modules import aggregate_modules
from codemap_aimemory.project_meta import build_project_meta

_FN_KINDS = frozenset({"method", "function"})
_CLS_KINDS = frozenset({"class", "interface"})

__all__ = ["AiMemoryEmitter"]


class AiMemoryEmitter:
    name: ClassVar[str] = "ai-memory"
    version: ClassVar[str] = "0.1.0"

    def emit(self, store: ReadOnlyStore, ctx: EmitContext) -> EmitResult:
        out_dir = _resolve_out_dir(ctx.output_dir)

        symbols = list(store.iter_symbols())
        edges = list(store.iter_edges())
        sid_str: dict[Any, str] = {s.id: str(s.id) for s in symbols}
        kinds: dict[str, str] = {sid_str[s.id]: s.kind for s in symbols}
        eid = build_entity_ids(list(kinds.keys()), kinds)
        known: set[str] = set(eid)
        enrichment = load_enrichment(out_dir / "enrichment")

        calls: defaultdict[str, list[str]] = defaultdict(list)
        called_by: defaultdict[str, list[str]] = defaultdict(list)
        related_tables: defaultdict[str, list[str]] = defaultdict(list)
        # Two-hop expansion: a Java method that maps_to a sql_mapping which
        # in turn accesses_table T should surface T in the method's
        # related_tables. We collect maps_to and accesses_table separately
        # first, then fan out maps_to sources onto the targets' tables.
        maps_to_src: defaultdict[str, list[str]] = defaultdict(list)
        accesses_by_src: defaultdict[str, list[str]] = defaultdict(list)
        rel_calls: list[dict[str, Any]] = []
        rel_tables: list[dict[str, Any]] = []

        for edge in edges:
            src = str(edge.source)
            tgt = str(edge.target)
            if src not in known or tgt not in known:
                continue
            if edge.kind == "calls":
                calls[src].append(eid[tgt])
                called_by[tgt].append(eid[src])
                rel_calls.append(
                    {
                        "from": eid[src],
                        "to": eid[tgt],
                        "type": "calls",
                        "confidence": edge.confidence,
                    }
                )
            elif edge.kind == "accesses_table":
                accesses_by_src[src].append(eid[tgt])
                related_tables[src].append(eid[tgt])
                rel_tables.append(
                    {
                        "from": eid[src],
                        "to": eid[tgt],
                        "type": "accesses_table",
                        "confidence": edge.confidence,
                    }
                )
            elif edge.kind == "maps_to":
                maps_to_src[src].append(tgt)

        # Fan out: for every java method that maps_to a sql_mapping, copy
        # that sql_mapping's table targets onto the method's related_tables.
        for method_sid, mapping_sids in maps_to_src.items():
            for mapping_sid in mapping_sids:
                for table_eid in accesses_by_src.get(mapping_sid, []):
                    if table_eid not in related_tables[method_sid]:
                        related_tables[method_sid].append(table_eid)

        functions: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        for sym in symbols:
            sid = sid_str[sym.id]
            enr = enrichment.get(sid, {})
            base = {
                "id": eid[sid],
                "symbol_id": sid,
                "file": str(sym.file),
                "line_range": [sym.range.start_line, sym.range.end_line],
                "signature": sym.signature,
                "confidence": sym.confidence,
                "change_count_90d": sym.extra.get("change_count_90d"),
                "business_meaning": enr.get("business_meaning"),
            }
            if sym.kind in _FN_KINDS:
                base["type"] = "function"
                base["calls"] = calls.get(sid, [])
                base["called_by"] = called_by.get(sid, [])
                base["related_tables"] = related_tables.get(sid, [])
                base["related_rules"] = enr.get("related_rules", [])
                functions.append(base)
            elif sym.kind in _CLS_KINDS:
                base["type"] = "class"
                base["calls"] = calls.get(sid, [])
                base["called_by"] = called_by.get(sid, [])
                base["related_tables"] = related_tables.get(sid, [])
                base["related_rules"] = enr.get("related_rules", [])
                functions.append(base)
            elif sym.kind == "table":
                base["type"] = "table"
                tables.append(base)

        files = sorted({str(s.file) for s in symbols})
        files_yml = [{"id": f"file-{i}", "path": p} for i, p in enumerate(files)]

        modules_yml = aggregate_modules(symbols, eid)
        all_entity_ids = list(eid.values()) + [m["id"] for m in modules_yml]
        outputs: dict[str, Any] = {
            "project.yml": build_project_meta(ctx.project_root),
            "entities/functions.yml": functions,
            "entities/tables.yml": tables,
            "entities/files.yml": files_yml,
            "entities/modules.yml": modules_yml,
            "relations/call-graph.yml": rel_calls,
            "relations/table-relations.yml": rel_tables,
            "relations/rule-constraints.yml": [],
            "_global/entities.yml": build_global_entities(out_dir, all_entity_ids),
        }
        written = _atomic_write_tree(out_dir, outputs)
        return EmitResult(files_written=written, diagnostics=[])


def _resolve_out_dir(out_dir: Path) -> Path:
    """The orchestrator passes ``<project>/.ai-memory`` already; treat any
    other path as the project root and append the standard subdir."""
    if out_dir.name == ".ai-memory":
        return out_dir
    return out_dir / ".ai-memory"


def _atomic_write_tree(out_dir: Path, outputs: dict[str, Any]) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, data in outputs.items():
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
            os.replace(tmp, target)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        written.append(rel)
    return written
