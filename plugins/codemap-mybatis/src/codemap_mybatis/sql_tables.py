"""Extract referenced table names + access mode from a (static) SQL string.

`codemap-sql` only parses DDL (``CREATE TABLE`` / ``CREATE VIEW`` /
``CREATE INDEX``); this module covers the DML side that MyBatis statements
need. Conservative regex over the four standard SQL verbs — good enough to
grade confidence per the indexer's static / dynamic / ``${}`` rule.
"""

from __future__ import annotations

import re

__all__ = ["table_refs"]

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"
_QUALIFIED_IDENT = rf"`?{_IDENT}`?(?:\s*\.\s*`?{_IDENT}`?)?"
# Negative-lookbehind keeps `DELETE FROM x` from matching the read regex too.
_READ_RE = re.compile(
    rf"(?<!DELETE\s)\b(?:FROM|JOIN)\s+({_QUALIFIED_IDENT})",
    re.IGNORECASE,
)
_WRITE_RE = re.compile(
    rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+({_QUALIFIED_IDENT})",
    re.IGNORECASE,
)


def _clean(name: str) -> str:
    return name.strip().strip("`").replace("`", "").strip()


def table_refs(sql: str) -> list[tuple[str, str]]:
    """Return ``(table_name, access)`` tuples, access ∈ {"read","write"}.

    Writes dominate reads for the same table: if a table appears in both a
    write and a read context within the same statement (e.g.
    ``INSERT INTO t SELECT * FROM t``), only ``(t, "write")`` is emitted so
    the caller never sees one logical table twice.
    """
    writes: list[str] = []
    reads: list[str] = []
    seen_writes: set[str] = set()
    seen_reads: set[str] = set()
    for m in _WRITE_RE.finditer(sql):
        name = _clean(m.group(1))
        if name not in seen_writes:
            seen_writes.add(name)
            writes.append(name)
    for m in _READ_RE.finditer(sql):
        name = _clean(m.group(1))
        if name not in seen_reads:
            seen_reads.add(name)
            reads.append(name)
    out: list[tuple[str, str]] = [(n, "write") for n in writes]
    out.extend((n, "read") for n in reads if n not in seen_writes)
    return out
