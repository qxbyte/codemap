# Changelog

All notable changes to CodeMap will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, MINOR may introduce breaking changes — they will be marked `BREAKING:`.

## [Unreleased]

### Added — Query commands (2026-05-30)

- `codemap search QUERY` — keyword search across symbol IDs / signatures / docs.
- `codemap get <symbol-id>` — fetch one symbol's definition site, doc, and a
  source-line snippet. Exits 1 if not found, 64 (`EX_USAGE`) on malformed
  SymbolID, 66 (`EX_NOINPUT`) when `.codemap/` is missing.
- `codemap callers <symbol-id> [-d N]` — every edge whose target matches the
  given id (depth-limited).
- `codemap callees <symbol-id> [-d N]` — every edge whose source matches.
- `codemap trace --from <id> [--to <id>] [-d N]` — BFS downstream walk or
  bidirectional shortest-path between two symbols, with rich-tree text output
  and a structured JSON envelope.
- `codemap routes [--method M]` — list every HTTP route the `http_route`
  bridge has registered, with handler `file:line` references.
- `codemap.core.graph` — depth-limited downstream `walk_chain` and
  bidirectional `shortest_path` (capped per-side, so `-d N` finds paths up
  to `2N` hops).
- All commands accept `--project / -p`, support `--json`, and use the same
  exit-code conventions (ADR-005). 14 graph unit tests + 19 end-to-end CLI
  tests cover the new surface. `docs/cli.md` documents every command and its
  JSON shape.

### Added — Sprint M-1 — HTTP route bridge (2026-05-30)

- `codemap.core.bridge.http_route.HttpRouteBridge` — first cross-language
  Bridge. Reads `Symbol.extra["http_route"]` (server-side) and
  `Symbol.extra["http_calls"]` (client-side) metadata and emits
  `Route` / `Alias` / `Edge` entries pivoting on a synthetic
  `scip-route` intermediate symbol per `(method, path)`.
- Path-variable matching (`/user/{id}` ↔ `/user/42`), context-path
  prefix joining (`context_path` + `path` → `full_path`), and query-string
  stripping on the client URL.
- Diagnostics: `ROUTE001` for duplicate server handlers on the same route;
  `ROUTE002` for high-confidence client calls with no matching server
  route. Low-confidence (dynamic) client URLs do not warn.
- Tests: 21 unit cases (covering empty inputs, malformed metadata,
  path-variable matching, cross-language aggregation, etc.) plus 1
  integration test wiring the Bridge through a real `JsonStore` round
  trip on disk. `docs/bridges/http_route.md` documents the metadata
  contract and known limitations.
- Registered via `[project.entry-points."codemap.bridges"] http_route =
  "codemap.core.bridge.http_route:HttpRouteBridge"` — on equal footing
  with any third-party Bridge (ADR-004).

### Added — Sprint N-1 — Python indexer (2026-05-30)

- `codemap.indexers.python.PythonIndexer` — first real-language indexer.
  Built on the stdlib `ast` module; produces `function` / `method` /
  `class` / `field` / `variable` symbols and `calls` / `imports` /
  `extends` edges. Diagnostics are isolated per file (syntax errors,
  non-UTF-8 sources do not abort a run).
- SymbolID scheme `scip-python`; the file path is encoded as a chain of
  `namespace` descriptors, matching the SCIP convention.
- 25 unit cases + 3 golden directory fixtures under
  `tests/fixtures/indexers/python/`. Dogfood baseline on this repository:
  48 files / 437 symbols / 1232 edges / 0 diagnostics.
- `docs/indexers/python.md` documents the resolution policy, the
  confidence ladder, and known limitations.

### Changed

- `JsonStore` integrity check now treats only missing edge **sources** as
  corruption; missing edge **targets** are normal (external library
  references the indexer did not cover). Design doc §6.4 updated to
  match.

### Added — Sprint 0 — Engineering scaffolding (2026-05-30)

- Project layout following ADR-003 (`core` / `io` / `indexers` / `cli` / `mcp` separation).
- `pyproject.toml` (Hatch backend) with quality-gate configuration: ruff, mypy strict, pytest, coverage, import-linter.
- `SymbolID` (SCIP format) with parse / `to_string` round-trip — ADR-001.
- Pydantic data models with `schema_version` enforcement — ADR-006.
- `SymbolStore` Protocol + JSON backend with atomic writes and file locking — ADR-002, ADR-008.
- `Indexer` / `Bridge` Protocols with entry_points registry — ADR-004.
- Typer CLI skeleton: `--version`, `--help`, `doctor`, `index`.
- Diagnostics: sysexits.h exit codes, structured logging — ADR-005.
- CI: GitHub Actions matrix (Python 3.11/3.12/3.13 × macOS/Linux), lint + type + test + build.
- ADRs 0001–0012 documenting Day-1 decisions (including ADR-L001 language neutrality).
- Reference indexer `_example_lang` to validate end-to-end pipeline.

[Unreleased]: https://github.com/qxbyte/codemap/compare/v0.0.0...HEAD
