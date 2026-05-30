"""Unit tests for the SQL indexer plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_sql import SqlIndexer
from codemap_sql.indexer import SCHEME

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, path: str = "schema.sql") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return SqlIndexer().index_file(
        Path(path),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="sql",
        ),
    )


def test_indexer_metadata() -> None:
    ix = SqlIndexer()
    assert ix.name == "sql"
    assert ix.languages == ["sql"]
    assert ix.supports(Path("a.sql"))
    assert ix.supports(Path("a.ddl"))
    assert not ix.supports(Path("a.py"))


def test_scheme_is_consistent() -> None:
    r = _index("CREATE TABLE u (id INT);")
    for s in r.symbols:
        assert str(s.id).startswith(f"{SCHEME} ")


def test_create_table_with_columns() -> None:
    r = _index(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        );
        """
    )
    tables = [s for s in r.symbols if s.kind == "class"]
    assert len(tables) == 1
    assert tables[0].extra.get("sql_kind") == "table"
    assert "users#" in str(tables[0].id)

    fields = [s for s in r.symbols if s.kind == "field"]
    field_names = {s.id.descriptors[-1].name for s in fields}
    assert field_names == {"id", "name", "email"}


def test_create_view() -> None:
    r = _index(
        """
        CREATE VIEW active_users AS
            SELECT * FROM users WHERE active = 1;
        """
    )
    view = next(s for s in r.symbols if s.kind == "class")
    assert view.extra.get("sql_kind") == "view"
    assert "active_users#" in str(view.id)


def test_create_index() -> None:
    r = _index("CREATE INDEX idx_users_email ON users(email);")
    indexes = [s for s in r.symbols if s.kind == "variable"]
    assert len(indexes) == 1
    assert indexes[0].extra.get("sql_kind") == "index"
    assert "idx_users_email." in str(indexes[0].id)


def test_columns_attached_to_table() -> None:
    r = _index(
        """
        CREATE TABLE products (
            sku TEXT PRIMARY KEY,
            price DECIMAL
        );
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    for f in fields:
        assert "products#" in str(f.id)


def test_multiple_tables_in_one_file() -> None:
    r = _index(
        """
        CREATE TABLE a (x INT);
        CREATE TABLE b (y INT);
        """
    )
    tables = [s for s in r.symbols if s.kind == "class"]
    assert {t.id.descriptors[-1].name for t in tables} == {"a", "b"}


def test_select_statements_ignored() -> None:
    r = _index(
        """
        CREATE TABLE u (id INT);
        SELECT * FROM u WHERE id = 1;
        INSERT INTO u VALUES (1);
        """
    )
    tables = [s for s in r.symbols if s.kind == "class"]
    # Only `u` from the CREATE TABLE; SELECT/INSERT don't add symbols.
    assert len(tables) == 1


def test_symbol_id_uses_path_namespaces() -> None:
    r = _index("CREATE TABLE u (id INT);", path="db/migrations/0001.sql")
    table = next(s for s in r.symbols if s.kind == "class")
    assert str(table.id) == "scip-sql . . . db/migrations/0001.sql/u#"


def test_lowercase_keywords_supported() -> None:
    r = _index("create table u (id int);")
    tables = [s for s in r.symbols if s.kind == "class"]
    assert len(tables) == 1


def test_empty_file_yields_no_symbols() -> None:
    r = _index("")
    assert r.symbols == []


def test_invalid_utf8_yields_diagnostic() -> None:
    ix = SqlIndexer()
    r = ix.index_file(
        Path("bad.sql"),
        b"\xff\xfe CREATE",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.sql"),
            language="sql",
        ),
    )
    assert r.symbols == []
    assert r.diagnostics[0].code == "SQL002"


def test_ddl_extension_supported() -> None:
    r = _index("CREATE TABLE t (id INT);", path="schema.ddl")
    assert any(s.kind == "class" for s in r.symbols)
