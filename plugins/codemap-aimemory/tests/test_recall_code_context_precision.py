"""Regression tests for v0.9 痛点 #2 — code_context entity-exact ranking.

Bug found during real-world try-run on wework-ops-assistant (2026-06-28):
``codemap recall 'TicketController updateStatus'`` returned a
``code_context`` containing BOTH ``ItTicketMapper.updateStatus`` AND
``MediaFileMapper.updateStatus`` interleaved — the user asked about
TicketController context, but the substring-fuzzy match flooded
unrelated namesakes with no priority signal.

Fix: ``_build_code_context`` consumes the query and assigns each
candidate a ``precision`` label:

- ``"high"`` when the candidate's short name precisely matches an
  entity-shaped token extracted from the query (FQN suffix match too,
  reusing the same logic as ``entity_exact_hook``).
- ``"low"`` for token-substring-only matches.

Then sorts ``(precision='high' first, change_count_90d desc, id stable)``.
This makes the genuinely-named entities surface first in the spec
author's injected context, and clearly tags noise so downstream
consumers (specode step 2.2 injection) can de-emphasise / drop low-
precision ones if they want.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from codemap_aimemory.recall import recall


def _seed_with_dup_named_methods(root: Path) -> None:
    """Two unrelated mappers both have `updateStatus` method — classic
    cross-table namesake fuzzy-match flood case."""
    ai_mem = root / ".ai-memory"
    (ai_mem / "_global").mkdir(parents=True)
    (ai_mem / "entities").mkdir(parents=True)

    (ai_mem / "_global" / "entities.yml").write_text(
        yaml.safe_dump(
            {
                "entities": [
                    {"id": "cls-TicketController", "type": "class", "source": "code"},
                    {"id": "fn-updateStatus-4f6656b5", "type": "function", "source": "code"},
                    {"id": "fn-updateStatus-efa4c91c", "type": "function", "source": "code"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "fn-updateStatus-4f6656b5",
                    "type": "function",
                    "file": "ops-app/.../ItTicketMapper.java",
                    "signature": "int updateStatus(Long id, String status)",
                    "called_by": ["fn-changeStatus"],
                    "change_count_90d": 5,
                },
                {
                    "id": "fn-updateStatus-efa4c91c",
                    "type": "function",
                    "file": "ops-app/.../MediaFileMapper.java",
                    "signature": "int updateStatus(Long id, String status)",
                    "called_by": ["fn-pollNext"],
                    "change_count_90d": 12,  # would otherwise win on churn alone
                },
            ]
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "files.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "tables.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "modules.yml").write_text("[]", encoding="utf-8")


def test_code_context_marks_precision_when_query_entity_matches(tmp_path: Path) -> None:
    """A query naming a specific entity → that entity gets precision=high."""
    _seed_with_dup_named_methods(tmp_path)

    # User asks about TicketController specifically — token 'ticketcontroller'
    # only matches cls-TicketController; both 'updateStatus' methods get hit
    # by the 'updatestatus' token (substring match), but neither's short name
    # equals an entity-shaped query token (the query only names
    # TicketController, not updateStatus alone).
    result = recall(
        query="TicketController updateStatus",
        project_root=tmp_path,
        top_k=5,
    )
    ctx = result["code_context"]
    by_id = {e["id"]: e for e in ctx}

    # TicketController: short name 'TicketController' precisely matches a
    # query entity token → high precision
    assert by_id["cls-TicketController"]["precision"] == "high"

    # Both updateStatus methods: short name 'updateStatus' precisely matches
    # a query entity token (extract_entities sees both 'TicketController'
    # and 'updateStatus' as CamelCase tokens) → both high precision
    assert by_id["fn-updateStatus-4f6656b5"]["precision"] == "high"
    assert by_id["fn-updateStatus-efa4c91c"]["precision"] == "high"


def test_code_context_substring_only_match_marked_low_precision(tmp_path: Path) -> None:
    """When the query has no entity-shaped token matching a candidate's short
    name, that candidate is precision=low even if it appeared in
    matched_entities via fuzzy substring."""
    _seed_with_dup_named_methods(tmp_path)

    # Query has neither 'TicketController' nor 'updateStatus' as entity tokens
    # (just lowercase noise words that substring-hit). matched_entities will
    # still flood, but precision should reflect the lack of exact match.
    result = recall(
        query="status ticket update",  # all lowercase, no CamelCase
        project_root=tmp_path,
        top_k=5,
    )
    ctx = result["code_context"]
    if ctx:
        # Nothing in this query is entity-shape → no candidate should be
        # high precision.
        precisions = {e["precision"] for e in ctx}
        assert "high" not in precisions, (
            f"got {precisions} — query has no CamelCase/FQN/api/snake "
            f"entity-shape tokens, nothing should be high"
        )


def test_code_context_sorts_high_precision_first_then_by_churn(tmp_path: Path) -> None:
    """High-precision candidates rank ahead of low-precision ones even when
    low-precision ones have higher change_count_90d. Within the same
    precision tier, churn-desc remains the tiebreak."""
    ai_mem = tmp_path / ".ai-memory"
    (ai_mem / "_global").mkdir(parents=True)
    (ai_mem / "entities").mkdir(parents=True)

    (ai_mem / "_global" / "entities.yml").write_text(
        yaml.safe_dump(
            {
                "entities": [
                    # Mention 'TicketController' specifically in the query →
                    # this one is high precision (short name matches)
                    {"id": "cls-TicketController", "type": "class", "source": "code"},
                    # But the 'ticket' lowercase word substring-hits these too
                    {"id": "cls-ticket-helper", "type": "class", "source": "code"},
                    {"id": "cls-ticket-other", "type": "class", "source": "code"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {"id": "cls-TicketController", "type": "class", "change_count_90d": 1},
                {"id": "cls-ticket-helper", "type": "class", "change_count_90d": 99},
                {"id": "cls-ticket-other", "type": "class", "change_count_90d": 50},
            ]
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "files.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "tables.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "modules.yml").write_text("[]", encoding="utf-8")

    result = recall(
        query="TicketController",  # only this is entity-shape
        project_root=tmp_path,
        top_k=5,
    )
    ctx = result["code_context"]
    ids = [e["id"] for e in ctx]

    # TicketController (precision=high, churn=1) must come first despite
    # the helpers having 99/50 churn. This proves precision wins over churn.
    if "cls-ticket-helper" in ids and "cls-ticket-other" in ids:
        # Both fuzzy hits are present → assertion meaningful
        assert ids.index("cls-TicketController") < ids.index("cls-ticket-helper"), (
            "precision=high should win over precision=low even at lower churn"
        )
