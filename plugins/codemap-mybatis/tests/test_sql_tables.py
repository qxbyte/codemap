"""Tests for DML table-reference extraction."""

from __future__ import annotations

from codemap_mybatis.sql_tables import table_refs


def test_simple_select_from() -> None:
    refs = table_refs("SELECT * FROM sf_coupon")
    assert ("sf_coupon", "read") in refs


def test_join_marks_as_read() -> None:
    refs = table_refs("SELECT * FROM sf_coupon c JOIN sf_user u ON c.uid = u.id")
    assert ("sf_coupon", "read") in refs
    assert ("sf_user", "read") in refs


def test_insert_into_marks_write() -> None:
    assert ("sf_coupon", "write") in table_refs("INSERT INTO sf_coupon (a) VALUES (1)")


def test_update_marks_write() -> None:
    assert ("sf_coupon", "write") in table_refs("UPDATE sf_coupon SET n = 1 WHERE id = 2")


def test_delete_marks_write() -> None:
    assert ("sf_coupon", "write") in table_refs("DELETE FROM sf_coupon WHERE id = 1")


def test_backticked_identifier_cleaned() -> None:
    refs = table_refs("SELECT * FROM `sf_coupon`")
    assert ("sf_coupon", "read") in refs


def test_qualified_identifier_kept() -> None:
    refs = table_refs("SELECT * FROM mydb.sf_coupon")
    # Qualified name preserved as-is; downstream consumers decide normalisation.
    assert any(r[0].endswith("sf_coupon") for r in refs)


def test_case_insensitive_verbs() -> None:
    assert ("sf_x", "read") in table_refs("select * from sf_x")
    assert ("sf_x", "write") in table_refs("update sf_x set a=1")


def test_no_dml_returns_empty() -> None:
    assert table_refs("CREATE TABLE x (id int)") == []
    assert table_refs("") == []


def test_write_dominates_over_read_for_same_table() -> None:
    refs = table_refs("INSERT INTO sf_coupon SELECT * FROM sf_coupon")
    # write comes first so it dominates; the same (name, access) pair isn't
    # duplicated, but both access modes can coexist for the same name.
    assert ("sf_coupon", "write") in refs
