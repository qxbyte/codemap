"""Tests for stable, unique ``entity_id`` derivation."""

from __future__ import annotations

from codemap_aimemory.ids import build_entity_ids, prefix_for, slug_base


def test_prefix_for_known_kinds() -> None:
    assert prefix_for("method") == "fn"
    assert prefix_for("function") == "fn"
    assert prefix_for("class") == "cls"
    assert prefix_for("interface") == "cls"
    assert prefix_for("table") == "tbl"
    assert prefix_for("route") == "route"
    assert prefix_for("field") == "field"
    assert prefix_for("sql_mapping") == "sql"


def test_prefix_for_unknown_kind_falls_back() -> None:
    assert prefix_for("totally_unknown") == "sym"


def test_slug_base_takes_last_descriptor_name() -> None:
    assert slug_base("scip-java . . . a/b/Foo.java/Foo#calc().") == "calc"


def test_single_symbol_no_suffix() -> None:
    sid = "scip-java . . . a/Foo.java/Foo#m()."
    mapping = build_entity_ids([sid], {sid: "method"})
    assert mapping == {sid: "fn-m"}


def test_collision_gets_hash_suffix_on_every_entry() -> None:
    sids = [
        "scip-java . . . a/Foo.java/Foo#m().",
        "scip-java . . . b/Bar.java/Bar#m().",
    ]
    kinds = dict.fromkeys(sids, "method")
    mapping = build_entity_ids(sids, kinds)
    vals = set(mapping.values())
    # both gain a hash suffix; the two entity ids are distinct
    assert len(vals) == 2
    assert all(v.startswith("fn-m-") for v in vals)


def test_distinct_simple_names_no_collision() -> None:
    sids = [
        "scip-java . . . a/F.java/F#calc().",
        "scip-java . . . a/F.java/F#load().",
    ]
    kinds = dict.fromkeys(sids, "method")
    mapping = build_entity_ids(sids, kinds)
    assert set(mapping.values()) == {"fn-calc", "fn-load"}


def test_kinds_drive_prefix() -> None:
    table_sid = "scip-table . . . sf_coupon#"
    fn_sid = "scip-java . . . a/F.java/F#calc()."
    mapping = build_entity_ids(
        [table_sid, fn_sid],
        {table_sid: "table", fn_sid: "method"},
    )
    assert mapping[table_sid] == "tbl-sf_coupon"
    assert mapping[fn_sid] == "fn-calc"


def test_missing_kind_uses_sym_prefix() -> None:
    sid = "scip-x . . . a/B/C#"
    mapping = build_entity_ids([sid])  # no kinds map
    assert mapping[sid] == "sym-C"


def test_determinism_stable_under_input_order() -> None:
    sids_a = ["scip-x . . . a/F#m().", "scip-x . . . b/F#m()."]
    sids_b = list(reversed(sids_a))
    kinds = dict.fromkeys(sids_a, "method")
    assert build_entity_ids(sids_a, kinds) == build_entity_ids(sids_b, kinds)
