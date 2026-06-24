# codemap-mybatis

MyBatis Mapper XML indexer plugin for [CodeMap](https://github.com/qxbyte/codemap).

## What it does

Reads MyBatis `*Mapper.xml` files and produces:

- `sql_mapping` symbols — one per `<select|insert|update|delete>` statement
- `table` symbols — one per referenced database table
- `accesses_table` edges — `sql_mapping → table`, with confidence graded
  by SQL complexity (static SQL → `high`; contains `<if>`/`<foreach>` → `medium`;
  uses `${}` substitution → `low`)
- `maps_to` edges — `java_method → sql_mapping`, linking the Java Mapper
  interface methods (produced by `codemap-java`) to their backing XML
  statements via `(namespace, stmt_id)`

## Scope

DDL (CREATE TABLE) lives in `codemap-sql`; this plugin handles the DML
side (FROM/JOIN/INSERT/UPDATE/DELETE) directly because it needs to grade
confidence by MyBatis dynamic-SQL constructs.

Dynamic SQL (`<if>`, `<foreach>`, `<where>`, `<set>`, `<choose>`, `<trim>`)
is extracted statically — the runtime-only branches are accepted as
medium-confidence edges. `${}` raw substitution (e.g. variable table
names) drops confidence to `low`.
