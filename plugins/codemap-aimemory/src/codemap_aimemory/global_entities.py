"""Global entity index — backs ``.ai-memory/_global/entities.yml`` (P1-2).

The four-layer memory model splits entity definitions across two layers:

* **L1 (code)** — codemap emits ``fn-*``, ``cls-*``, ``tbl-*``, ``mod-*``
  as it walks the source tree.
* **L2/L3 (knowledge)** — ``spec-distill v2`` writes
  ``.ai-memory/knowledge/{rules,business,modules,cases,pitfalls}/*.yml``
  that reference code entities via ``related_code[].entity`` and link
  to sibling knowledge via ``related_knowledge``.

Until now the two halves only intersected at read time; a downstream
Agent answering "where is ``sf_coupon`` referenced?" had to walk both
halves itself. ``build_global_entities()`` does that walk once at emit
time and writes a single ``_global/entities.yml`` lookup so retrieval
(roadmap P3) can hit it directly.

Output shape::

    schema_version: "1.0"
    generated_at: 2026-06-25
    counts:
      total: N
      code_only: A
      knowledge_only: B
      both: C
    entities:
      - id: fn-calc
        type: function                 # function / class / table / module / unknown
        source: both                   # code / knowledge / both
        knowledge_refs:                # knowledge_ids that mention this entity
          - rule-coupon-mutex
          - case-REQ-2024-0078

Pure function — no IO outside ``yaml.safe_load`` on knowledge yml.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

__all__ = ["build_global_entities"]


_KNOWLEDGE_SUBDIRS: tuple[str, ...] = (
    "rules",
    "business",
    "modules",
    "cases",
    "pitfalls",
)


def build_global_entities(
    out_dir: Path,
    code_entity_ids: Iterable[str],
) -> dict[str, Any]:
    """Cross-walk code entities and knowledge yml references.

    ``out_dir`` is the ``.ai-memory/`` root — knowledge is read from
    ``out_dir/knowledge/<subdir>/*.yml``. Missing directories are tolerated:
    on a fresh project with no knowledge yet, every entity is ``code_only``.
    """
    code_ids = set(code_entity_ids)
    references: dict[str, set[str]] = {}
    knowledge_ids: set[str] = set()  # ids defined by knowledge files themselves

    knowledge_root = out_dir / "knowledge"
    if knowledge_root.is_dir():
        for subdir in _KNOWLEDGE_SUBDIRS:
            for yml_file in sorted((knowledge_root / subdir).glob("*.yml")):
                _ingest_knowledge_yml(yml_file, references, knowledge_ids)

    all_ids = code_ids | knowledge_ids | set(references.keys())
    entities: list[dict[str, Any]] = []
    code_only = knowledge_only = both = 0
    for eid in sorted(all_ids):
        in_code = eid in code_ids
        refs = sorted(references.get(eid, set()))
        in_knowledge = bool(refs)
        if in_code and in_knowledge:
            source = "both"
            both += 1
        elif in_code:
            source = "code"
            code_only += 1
        else:
            source = "knowledge"
            knowledge_only += 1
        entities.append(
            {
                "id": eid,
                "type": _entity_type_from_id(eid),
                "source": source,
                "knowledge_refs": refs,
            }
        )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "counts": {
            "total": len(entities),
            "code_only": code_only,
            "knowledge_only": knowledge_only,
            "both": both,
        },
        "entities": entities,
    }


def _ingest_knowledge_yml(
    yml_file: Path,
    references: dict[str, set[str]],
    knowledge_ids: set[str],
) -> None:
    """Read one knowledge yml, register its own id + every entity it points at.

    Looks at three reference channels:

    * ``related_code[].entity`` — explicit code-entity link
    * ``related_knowledge[]`` — sibling knowledge ids
    * ``affects[]`` — for pitfalls; treats list entries as code-ish ids

    Unknown / malformed yml is silently skipped — the emitter must not
    crash mid-build because someone hand-edited a knowledge file.
    """
    try:
        text = yml_file.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return
    if not isinstance(data, dict):
        return

    knowledge_id = data.get("knowledge_id") or yml_file.stem
    if not isinstance(knowledge_id, str):
        return

    knowledge_ids.add(knowledge_id)
    for ref in _iter_entity_refs(data):
        if ref == knowledge_id:
            continue  # don't self-reference
        references.setdefault(ref, set()).add(knowledge_id)


def _iter_entity_refs(data: dict[str, Any]) -> Iterable[str]:
    related_code = data.get("related_code")
    if isinstance(related_code, list):
        for item in related_code:
            if isinstance(item, dict):
                entity = item.get("entity")
                if isinstance(entity, str) and entity:
                    yield entity

    related_knowledge = data.get("related_knowledge")
    if isinstance(related_knowledge, list):
        for item in related_knowledge:
            if isinstance(item, str) and item:
                yield item

    affects = data.get("affects")
    if isinstance(affects, list):
        for item in affects:
            # `affects` carries file paths for pitfalls — only surface
            # entries that look like an entity_id (prefix-...). Plain
            # file paths are skipped to avoid polluting the index.
            if isinstance(item, str) and "-" in item and "/" not in item:
                yield item


def _entity_type_from_id(eid: str) -> str:
    prefix = eid.split("-", 1)[0] if "-" in eid else ""
    return {
        "fn": "function",
        "cls": "class",
        "tbl": "table",
        "mod": "module",
        "rule": "rule",
        "biz": "business_process",
        "case": "case",
        "pit": "pitfall",
        "file": "file",
    }.get(prefix, "unknown")
