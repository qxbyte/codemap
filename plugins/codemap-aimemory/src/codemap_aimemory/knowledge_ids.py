"""Single derivation of knowledge_id slugs (FIX-2 / AI-EDS ISSUE-2).

Both knowledge-writing channels (task-swarm auto-ingest and specode-distill)
derive their ids here, so the same logical knowledge gets the **same id** and
the documented "distill supersedes the auto case" merge actually fires.

* ``case_id(spec_id)``   → ``case-<kebab(spec_id)>`` (one canonical case per spec)
* ``pit_id(signature)``  → ``pit-<kebab(signature)>``
* ``derive_id(cat,name)``→ ``<prefix>-<kebab(name)>``
* ``normalize_id(cat,raw)`` ensures the category prefix is present + kebab-clean

stdlib-only; deterministic; mirrors ``ids.py``'s hash-fallback philosophy so
ids stay stable.
"""

from __future__ import annotations

import hashlib
import re

from codemap_aimemory.knowledge_schema import ID_PREFIX

__all__ = ["case_id", "derive_id", "kebab", "normalize_id", "pit_id"]

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def kebab(text: str) -> str:
    """Lowercase ASCII kebab-case. Falls back to a stable short hash when no
    ASCII alphanumerics survive (e.g. an all-CJK title), never returns empty."""
    lowered = (text or "").lower()
    slug = _NON_SLUG.sub("-", lowered).strip("-")
    if slug:
        return slug
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]
    return digest


def normalize_id(category: str, raw: str) -> str:
    """Return a kebab-clean id carrying ``category``'s prefix.

    Idempotent: an id already starting with the prefix is only re-kebabed,
    not double-prefixed.
    """
    prefix = ID_PREFIX.get(category)
    if prefix is None:
        return kebab(raw)
    slug = kebab(raw)
    if slug == prefix or slug.startswith(prefix + "-"):
        return slug
    return f"{prefix}-{slug}"


def derive_id(category: str, name: str) -> str:
    return normalize_id(category, name)


def case_id(spec_id: str) -> str:
    return normalize_id("cases", spec_id)


def pit_id(signature: str) -> str:
    return normalize_id("pitfalls", signature)
