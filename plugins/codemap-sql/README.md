# codemap-sql

> A SQL indexer for [CodeMap](https://github.com/qxbyte/codemap), shipped
> as an independent PyPI package.

Indexes DDL (schema) statements so AI agents can answer "which table has
column X" and similar structural questions without scanning every
migration file. Query (`SELECT`/`INSERT`/...) statements are ignored —
they are not durable schema artefacts.

## What it captures

Backed by `tree-sitter-sql`:

| AST node | Symbol kind |
|---|---|
| `create_table` | `class` (with `extra.sql_kind=table`) |
| `create_view` | `class` (with `extra.sql_kind=view`) |
| `create_index` | `variable` (with `extra.sql_kind=index`) |
| `column_definition` inside `create_table` | `field` (attached to the table) |

Asset-style scheme: this plugin uses ``scip-sql`` so a downstream
``http_route`` / ``orm_mapping`` bridge can cross-reference these
symbols against application code that talks to them.

## SymbolID encoding

```
scip-sql . . . db/migrations/0001_init.sql/users#
scip-sql . . . db/migrations/0001_init.sql/users#email.
scip-sql . . . db/migrations/0001_init.sql/idx_users_email.
```

## Install

```bash
pip install codemap-sql
```

## Limits

* Only DDL is indexed; `SELECT` / `INSERT` / `UPDATE` / `DELETE` are
  walked past silently.
* `CREATE PROCEDURE` / `CREATE FUNCTION` / `CREATE TRIGGER` are not
  yet captured — the grammar reports them under generic statement nodes.
* Dialect-specific features (e.g. PostgreSQL extensions) may not be
  parsed.
* `ALTER TABLE` statements that add columns are not tracked.

## License

MIT.
