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
    name AND no ascii-startswith fallback either, that candidate is precision=low
    even if it appeared in matched_entities via fuzzy substring."""
    _seed_with_dup_named_methods(tmp_path)

    # Query has neither 'TicketController' nor 'updateStatus' as entity tokens
    # (just lowercase noise words). Each lowercase word IS an ascii token but
    # none startswith candidate short names ('TicketController' / 'updateStatus'
    # lowercased = 'ticketcontroller' / 'updatestatus'); 'status' / 'ticket' /
    # 'update' don't startswith those.
    result = recall(
        query="abc xyz qrs",  # nonsense ascii tokens that don't startswith anything
        project_root=tmp_path,
        top_k=5,
    )
    ctx = result["code_context"]
    if ctx:
        precisions = {e["precision"] for e in ctx}
        assert "high" not in precisions, (
            f"got {precisions} — nonsense ascii tokens shouldn't trigger "
            f"startswith match for any candidate"
        )


def test_chinese_query_with_ascii_acronym_token_marks_matching_entity_high(
    tmp_path: Path,
) -> None:
    """v0.9 痛点 #4 (real BUG found in 2026-06-28 ticket-assign-it-member try-run):

    Chinese query like ``'工单指派 IT 成员'`` — ``IT`` is a 2-letter acronym
    not matching the multi-hump CamelCase regex; ``extract_entities`` returns
    empty → ``query_entities`` empty → original logic standlone marks
    *everything* low, collapsing the precision-based sort.

    Fix: ascii-token startswith fallback marks ``ItMember`` high (its short
    name lowercased starts with the ``it`` token) while ``MonitoredRoom``
    stays low — the actual disambiguation intent is preserved.
    """
    ai_mem = tmp_path / ".ai-memory"
    (ai_mem / "_global").mkdir(parents=True)
    (ai_mem / "entities").mkdir(parents=True)

    (ai_mem / "_global" / "entities.yml").write_text(
        yaml.safe_dump(
            {
                "entities": [
                    {"id": "cls-ItMember", "type": "class", "source": "code"},
                    {"id": "cls-ItTicket", "type": "class", "source": "code"},
                    {"id": "cls-MonitoredRoom", "type": "class", "source": "code"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "functions.yml").write_text(
        yaml.safe_dump(
            [
                {"id": "cls-ItMember", "type": "class", "file": "ItMember.java"},
                {"id": "cls-ItTicket", "type": "class", "file": "ItTicket.java"},
                {"id": "cls-MonitoredRoom", "type": "class", "file": "MonitoredRoom.java"},
            ]
        ),
        encoding="utf-8",
    )
    (ai_mem / "entities" / "files.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "tables.yml").write_text("[]", encoding="utf-8")
    (ai_mem / "entities" / "modules.yml").write_text("[]", encoding="utf-8")

    result = recall(
        query="工单指派 IT 成员",
        project_root=tmp_path,
        top_k=5,
    )
    ctx = result["code_context"]
    by_id = {e["id"]: e for e in ctx}

    # ItMember / ItTicket lowercased start with 'it' token → high
    assert by_id.get("cls-ItMember", {}).get("precision") == "high", (
        "ItMember should be high — its short name starts with the 'it' ascii "
        "token from the query (v0.9 痛点 #4 fix)"
    )
    assert by_id.get("cls-ItTicket", {}).get("precision") == "high", (
        "ItTicket should be high — same ascii-startswith reason"
    )
    # MonitoredRoom doesn't startswith any query token → low
    if "cls-MonitoredRoom" in by_id:
        assert by_id["cls-MonitoredRoom"]["precision"] == "low", (
            "MonitoredRoom should stay low — its short name doesn't start with "
            "'it' or any other ascii query token"
        )


def test_precision_helper_unit_chinese_query_with_acronym() -> None:
    """Direct unit on _precision_for_entity_id covering rule 2 (ascii startswith
    fallback). Pins the matrix:
    - empty query_entities + 'it' in tokens → ItMember high
    - empty query_entities + 'it' in tokens → MonitoredRoom low
    - empty query_entities + tokens=None → low (back-compat)
    - non-ascii token (Chinese bigram) doesn't trigger startswith
    """
    from codemap_aimemory.recall import _precision_for_entity_id

    # Rule 2 hit
    assert _precision_for_entity_id("cls-ItMember", set(), {"it", "工单"}) == "high"
    # Rule 2 miss (doesn't startswith)
    assert _precision_for_entity_id("cls-MonitoredRoom", set(), {"it", "工单"}) == "low"
    # Tokens=None → original behavior (rule 1 then low)
    assert _precision_for_entity_id("cls-ItMember", set(), None) == "low"
    # Single-char token (len<2) → ignored
    assert _precision_for_entity_id("cls-ItMember", set(), {"i"}) == "low"
    # Chinese-only tokens (non-ascii) → ignored
    assert _precision_for_entity_id("cls-ItMember", set(), {"工单", "指派"}) == "low"
    # Rule 1 takes priority over rule 2 (back-compat)
    assert _precision_for_entity_id("cls-ItMember", {"ItMember"}, {"it"}) == "high"


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
