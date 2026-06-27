"""FIX-3c — entity-exact recall hook.

When the query precisely names a table / class / api-path / FQN, this
hook surfaces every knowledge whose ``related_code[].entity`` list
contains a match. Higher overlap ranks first.

Registered into ``codemap.recall_hooks`` so it composes through the
existing RRF fuser; no surgery on :mod:`codemap_aimemory.recall` and
the token / embedding paths are untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from codemap_aimemory.knowledge_schema import CATEGORIES, CATEGORY_TYPE
from codemap_aimemory.recall import extract_entities

__all__ = ["rank"]


def rank(
    *,
    query: str,
    project_root: Path,
    base_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic entity-precision ranker.

    ``base_candidates`` is part of the hook contract but unused here:
    we scan the knowledge tree ourselves so an entity hit is found even
    when the token path missed (e.g. the query mentions ``sf_order`` but
    the rule's statement is in Chinese).
    """
    entities = extract_entities(query)
    if not entities:
        return []

    knowledge_root = project_root / ".ai-memory" / "knowledge"
    if not knowledge_root.is_dir():
        return []

    wanted = set(entities)
    hits: list[tuple[int, list[str], dict[str, Any], str]] = []

    for category in CATEGORIES:
        category_dir = knowledge_root / category
        if not category_dir.is_dir():
            continue
        for yml_file in sorted(category_dir.glob("*.yml")):
            kn = _load_yaml(yml_file)
            if not isinstance(kn, dict):
                continue
            matched = _matched_entities(kn, wanted)
            if not matched:
                continue
            hits.append((len(matched), matched, kn, category))

    # Most matches first; tie-break by knowledge_id for determinism.
    hits.sort(key=lambda h: (-h[0], h[2].get("knowledge_id") or ""))

    return [_to_candidate(matched, kn, category) for _, matched, kn, category in hits]


def _matched_entities(knowledge: dict[str, Any], wanted: set[str]) -> list[str]:
    related = knowledge.get("related_code") or []
    if not isinstance(related, list):
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for entry in related:
        if not isinstance(entry, dict):
            continue
        ent = entry.get("entity")
        if not isinstance(ent, str) or ent in seen:
            continue
        if any(_entity_match(q, ent) for q in wanted):
            seen.add(ent)
            matched.append(ent)
    return matched


def _entity_match(query_ent: str, kn_ent: str) -> bool:
    """Match an entity from the query against one declared in a knowledge's
    ``related_code``. Either form may carry a dotted package prefix; we
    treat the short suffix as the canonical identity, so
    ``com.helloshop.order.OrderController`` and ``OrderController`` are
    the same class. Equality alone would miss this common Java/Python idiom.
    """
    if query_ent == kn_ent:
        return True
    if "." in kn_ent and kn_ent.rsplit(".", 1)[-1] == query_ent:
        return True
    return bool("." in query_ent and query_ent.rsplit(".", 1)[-1] == kn_ent)


def _to_candidate(matched: list[str], kn: dict[str, Any], category: str) -> dict[str, Any]:
    kid = kn.get("knowledge_id")
    return {
        "knowledge_id": kid,
        "category": category,
        "type": kn.get("type") or CATEGORY_TYPE.get(category),
        "title": _title_of(kn),
        "matched_entities": matched,
    }


def _title_of(kn: dict[str, Any]) -> str:
    for field in ("title", "statement", "symptom", "implementation_summary", "scope", "trigger"):
        value = kn.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0][:120]
    return kn.get("knowledge_id") or ""


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
