"""Single authority for the 5-category knowledge contract (FIX-2 / RC-B).

`.ai-memory/knowledge/{rules,business,modules,cases,pitfalls}/*.yml` used to
have its schema defined three independent times:

* task-swarm ``_ingest_lessons`` hand-rolled the case/pitfall dicts,
* specode-distill described it as markdown templates the LLM filled,
* ``recall.py`` listed the searchable / content field names a fourth time.

Any one drifting silently broke the others (AI-EDS ISSUE-5). This module is
the **one place** the category set, the category→type map, the id prefixes,
the common fields and the per-category content fields are defined. ``recall``
imports from here; the writer (``knowledge_writer``) and the CLI validate
against here; task-swarm and specode-distill feed payloads shaped by here.

Pure constants + a stdlib-only ``validate`` — no IO, no third-party deps.
"""

from __future__ import annotations

__all__ = [
    "CATEGORIES",
    "CATEGORY_TYPE",
    "COMMON_FIELDS",
    "CONTENT_FIELDS_BY_CATEGORY",
    "ID_PREFIX",
    "SCHEMA_VERSION",
    "validate",
]

SCHEMA_VERSION = "1.0"

#: Canonical ordering — also the on-disk subdirectory names under
#: ``.ai-memory/knowledge/`` and ``knowledge-base/``.
CATEGORIES: tuple[str, ...] = ("rules", "business", "modules", "cases", "pitfalls")

#: category → the ``type`` field value every knowledge in that category carries.
CATEGORY_TYPE: dict[str, str] = {
    "rules": "business_rule",
    "business": "business_process",
    "modules": "module_map",
    "cases": "case",
    "pitfalls": "pitfall",
}

#: category → knowledge_id prefix (``rule-`` / ``biz-`` / ``mod-`` / ``case-``
#: / ``pit-``).
ID_PREFIX: dict[str, str] = {
    "rules": "rule",
    "business": "biz",
    "modules": "mod",
    "cases": "case",
    "pitfalls": "pit",
}

#: Fields every category's yml carries (identity + provenance + linkage).
COMMON_FIELDS: tuple[str, ...] = (
    "schema_version",
    "knowledge_id",
    "type",
    "version",
    "created_at",
    "updated_at",
    "status",
    "confidence",
    "source_spec",
    "source_files",
    "related_requirements",
    "related_knowledge",
    "related_code",
    "tags",
)

#: category → the core semantic fields. Mirrors recall.py's historical
#: ``_CONTENT_FIELDS_BY_CATEGORY`` exactly so ``--with-content`` stays stable.
CONTENT_FIELDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "rules": (
        "statement",
        "why",
        "trigger_conditions",
        "exceptions",
        "enforcement",
    ),
    "business": (
        "trigger",
        "end_state",
        "steps",
        "data_flow",
        "ui_constraints",
    ),
    "modules": (
        "scope",
        "primary_entity",
        "columns",
        "shard",
        "call_chain",
    ),
    "cases": (
        "implementation_summary",
        "key_decisions",
        "bugs_encountered",
        "lessons",
        "review_findings",
        "acceptance_status",
        "changed_files",
    ),
    "pitfalls": (
        "symptom",
        "root_cause",
        "fix",
        "prevention",
        "affects",
    ),
}

#: Common fields that must be present + non-empty for a knowledge to lint clean.
_REQUIRED_COMMON: tuple[str, ...] = (
    "knowledge_id",
    "type",
    "version",
    "created_at",
    "updated_at",
    "status",
    "confidence",
)


def validate(knowledge: dict, category: str) -> list[str]:
    """Return a list of human-readable lint errors (empty == clean).

    Checks: category is known · required common fields present · ``type``
    matches the category · ``knowledge_id`` carries the category's prefix ·
    ``version`` is a positive int.
    """
    errors: list[str] = []

    if category not in CATEGORIES:
        errors.append(f"unknown category: {category!r} (expected one of {CATEGORIES})")
        return errors

    for field in _REQUIRED_COMMON:
        value = knowledge.get(field)
        if value in (None, "", [], {}):
            errors.append(f"missing required field: {field}")

    expected_type = CATEGORY_TYPE[category]
    actual_type = knowledge.get("type")
    if actual_type is not None and actual_type != expected_type:
        errors.append(
            f"type mismatch: category {category!r} expects type "
            f"{expected_type!r}, got {actual_type!r}"
        )

    kid = knowledge.get("knowledge_id")
    if isinstance(kid, str) and kid:
        prefix = ID_PREFIX[category] + "-"
        if not kid.startswith(prefix):
            errors.append(f"knowledge_id {kid!r} must start with category prefix {prefix!r}")

    version = knowledge.get("version")
    if version is not None and (not isinstance(version, int) or version < 1):
        errors.append(f"version must be a positive int, got {version!r}")

    return errors
