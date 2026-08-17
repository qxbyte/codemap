"""MyBatis Mapper XML indexer.

Parses ``<mapper namespace="...">`` files and produces:

* one ``sql_mapping`` symbol per ``<select|insert|update|delete>``, keyed by
  ``(namespace, statement-id)``; carries ``extra["java_namespace"]`` and
  ``extra["java_method_name"]`` so the :class:`MyBatisLinkBridge` can later
  cross-reference back to the Java Mapper interface method that owns it.
* one ``table`` symbol per referenced DB table (deduped per file).
* an ``accesses_table`` edge from each ``sql_mapping`` to every table it
  references, with confidence graded by SQL complexity (static → ``high``;
  contains dynamic tags → ``medium``; uses ``${}`` substitution → ``low``).

The Java ↔ XML cross-link (``maps_to`` edges) is the bridge's job, not this
per-file indexer — by design (ADR-0004 separation of indexers and bridges).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import ClassVar

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version
from codemap_mybatis.sql_tables import table_refs

__all__ = ["SCHEME_MAPPING", "SCHEME_TABLE", "MyBatisIndexer"]

SCHEME_MAPPING = "scip-mybatis"
SCHEME_TABLE = "scip-table"
LANG_MYBATIS = "mybatis"
LANG_SQL = "sql"

_STMT_TAGS = frozenset({"select", "insert", "update", "delete"})
_DYNAMIC_TAGS = frozenset({"if", "foreach", "choose", "where", "set", "trim", "when", "otherwise"})
_SUBSTITUTION_RE = re.compile(r"\$\{")


class MyBatisIndexer:
    name: ClassVar[str] = "mybatis"
    version: ClassVar[str] = package_version("codemap-mybatis")
    file_patterns: ClassVar[list[str]] = ["*.xml"]
    languages: ClassVar[list[str]] = [LANG_MYBATIS]

    def supports(self, path: Path) -> bool:
        if path.suffix != ".xml":
            return False
        try:
            head = path.read_bytes()[:4096]
        except OSError:
            return False
        return b"<mapper" in head and b"namespace" in head

    def index_file(self, path: Path, source: bytes, ctx: IndexContext) -> IndexResult:
        try:
            root = ET.fromstring(source)
        except ET.ParseError as exc:
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        file=ctx.relative_path,
                        code="MB001",
                        message=f"XML parse error: {exc}",
                        producer=self.name,
                    )
                ]
            )
        if root.tag != "mapper":
            return IndexResult()
        namespace = root.get("namespace", "")
        if not namespace:
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="warning",
                        file=ctx.relative_path,
                        code="MB002",
                        message="mapper element missing namespace attribute",
                        producer=self.name,
                    )
                ]
            )

        symbols: list[Symbol] = []
        edges: list[Edge] = []
        emitted_tables: set[str] = set()

        for child in root:
            tag = child.tag.lower()
            if tag not in _STMT_TAGS:
                continue
            stmt_id = child.get("id")
            if not stmt_id:
                continue
            mapping_sid = _mapping_id(ctx.relative_path, namespace, stmt_id)
            symbols.append(
                Symbol(
                    id=mapping_sid,
                    kind="sql_mapping",
                    language=LANG_MYBATIS,
                    file=ctx.relative_path,
                    range=Range(start_line=1, end_line=1),
                    confidence="high",
                    extra={
                        "java_namespace": namespace,
                        "java_method_name": stmt_id,
                        "sql_verb": tag,
                    },
                )
            )

            raw_sql = "".join(child.itertext())
            conf = _confidence_for(raw_sql, child)
            for table_name, _access in table_refs(raw_sql):
                table_sid = _table_id(table_name)
                if table_name not in emitted_tables:
                    symbols.append(
                        Symbol(
                            id=table_sid,
                            kind="table",
                            language=LANG_SQL,
                            file=ctx.relative_path,
                            range=Range(start_line=1, end_line=1),
                            confidence="high",
                        )
                    )
                    emitted_tables.add(table_name)
                edges.append(
                    Edge(
                        source=mapping_sid,
                        target=table_sid,
                        kind="accesses_table",
                        confidence=conf,
                    )
                )

        return IndexResult(symbols=symbols, edges=edges)


# ---------------------------------------------------------------------------
# SymbolID builders
# ---------------------------------------------------------------------------


def _mapping_id(rel_path: PurePosixPath, namespace: str, stmt_id: str) -> SymbolID:
    """``scip-mybatis . . . src/mapper/CouponMapper.xml/com.example.CouponMapper#selectByUser.``"""
    descriptors: list[Descriptor] = [
        Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in rel_path.parts
    ]
    descriptors.append(Descriptor(name=namespace, kind=DescriptorKind.TYPE))
    descriptors.append(Descriptor(name=stmt_id, kind=DescriptorKind.TERM))
    return SymbolID(scheme=SCHEME_MAPPING, descriptors=tuple(descriptors))


def _table_id(table_name: str) -> SymbolID:
    return SymbolID(
        scheme=SCHEME_TABLE,
        descriptors=(Descriptor(name=table_name, kind=DescriptorKind.TYPE),),
    )


def _confidence_for(sql: str, stmt_node: ET.Element) -> str:
    """Grade SQL extraction confidence.

    Order matters: ``${}`` substitution dominates because the table name
    itself may be unknown; dynamic tags merely shave the WHERE clause.
    """
    if _SUBSTITUTION_RE.search(sql):
        return "low"
    if any(_has_dynamic_child(stmt_node)):
        return "medium"
    return "high"


def _has_dynamic_child(node: ET.Element):  # type: ignore[no-untyped-def]
    for child in node.iter():
        if child is node:
            continue
        if child.tag.lower() in _DYNAMIC_TAGS:
            yield True
            return
    yield False
