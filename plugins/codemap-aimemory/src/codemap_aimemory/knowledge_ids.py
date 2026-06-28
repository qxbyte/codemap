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

#: Total id max length (含 prefix)。v0.4.8 加 — round 3 试跑实测:
#: 长 title 派生出 ~150 字符 id, 文件系统 + 可读性都差。80 是个常见的
#: filename-safe 上限(POSIX guarantees 255 but git / zip / windows paths
#: get awkward past ~80)。
ID_MAX_LEN = 80

#: 超长 slug 截断时附加的稳定短哈希长度(保证唯一性 / collision 概率低)。
_TRUNC_HASH_LEN = 8


def kebab(text: str) -> str:
    """Lowercase ASCII kebab-case. Falls back to a stable short hash when no
    ASCII alphanumerics survive (e.g. an all-CJK title), never returns empty."""
    lowered = (text or "").lower()
    slug = _NON_SLUG.sub("-", lowered).strip("-")
    if slug:
        return slug
    digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]
    return digest


def _truncate_slug(slug: str, max_slug_len: int, source: str) -> str:
    """Truncate ``slug`` to ``max_slug_len`` chars while keeping uniqueness.

    Strategy: keep ``max_slug_len - 1 - _TRUNC_HASH_LEN`` leading chars (cut at
    a kebab boundary if possible), then append ``-<8-hex-hash-of-source>`` so
    that two different long titles never collide after truncation. ``source``
    is the **original** text (pre-kebab) so collision is computed on the
    full input, not the truncated slug.

    v0.4.8 (round 3 实测): writer 之前从 title 派生 150+ char id 文件名,
    既不友好也踩 fs/git path 边界; max length 80 + hash suffix 是工业界
    常用 slug 截断惯例(slugify libraries 都这么做)。
    """
    if len(slug) <= max_slug_len:
        return slug
    keep = max_slug_len - 1 - _TRUNC_HASH_LEN  # 1 for the joining "-"
    if keep < 1:
        # max_slug_len 太小, hash 全填(极端边界, 理论不该到)
        return hashlib.sha1(source.encode("utf-8")).hexdigest()[:max_slug_len]
    # Try to cut at last "-" within keep to avoid breaking a word mid-segment
    truncated = slug[:keep]
    last_dash = truncated.rfind("-")
    if last_dash >= keep - 12:  # only cut at boundary if it's not too lossy
        truncated = truncated[:last_dash]
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:_TRUNC_HASH_LEN]
    return f"{truncated}-{digest}"


def normalize_id(category: str, raw: str) -> str:
    """Return a kebab-clean id carrying ``category``'s prefix.

    Idempotent: an id already starting with the prefix is only re-kebabed,
    not double-prefixed.

    v0.4.8: total id length capped at :data:`ID_MAX_LEN` chars. When slug
    portion alone would push past the cap, the slug is truncated and
    suffixed with a short stable hash of the original input so collisions
    are avoided.
    """
    prefix = ID_PREFIX.get(category)
    slug = kebab(raw)
    if prefix is None:
        return _truncate_slug(slug, ID_MAX_LEN, raw)
    # Idempotent: skip double-prefixing if input already has the prefix
    if slug == prefix or slug.startswith(prefix + "-"):
        return _truncate_slug(slug, ID_MAX_LEN, raw)
    # Reserve room for "<prefix>-" before the slug
    max_slug_len = ID_MAX_LEN - len(prefix) - 1  # 1 for the joining "-"
    return f"{prefix}-{_truncate_slug(slug, max_slug_len, raw)}"


def derive_id(category: str, name: str) -> str:
    return normalize_id(category, name)


def case_id(spec_id: str) -> str:
    return normalize_id("cases", spec_id)


def pit_id(signature: str) -> str:
    return normalize_id("pitfalls", signature)
