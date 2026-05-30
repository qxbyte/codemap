# Changelog

All notable changes to CodeMap will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, MINOR may introduce breaking changes — they will be marked `BREAKING:`.

## [Unreleased]

### Added — Swift, Kotlin, Ruby, PHP independent PyPI plugins (2026-05-30)

- `plugins/codemap-swift/` — `tree-sitter-swift` backed. Class / struct /
  enum / protocol kept under `extra.swift_kind`; functions and `init`
  inside types become methods; top-level `let`/`var` become variables.
  14 unit tests. Scheme `scip-swift`.
- `plugins/codemap-kotlin/` — `tree-sitter-kotlin` backed. Class /
  interface / object under `extra.kotlin_kind`, package header captured
  as `extra.package`, `fun` inside type → method, top-level `val`/`var`
  → variable. Supports both `.kt` and `.kts`. 14 unit tests. Scheme
  `scip-kotlin`.
- `plugins/codemap-ruby/` — `tree-sitter-ruby` backed. Class / module
  under `extra.ruby_kind`, top-level `def` → function, `def` inside
  type → method, `def self.x` → method with `extra.ruby_kind=singleton`.
  Nested module/class produces qualified `Outer#Inner#m()` IDs. 13 unit
  tests. Scheme `scip-ruby`.
- `plugins/codemap-php/` — `tree-sitter-php` backed. Class / interface /
  trait / enum under `extra.php_kind`, `namespace_definition` captured
  as `extra.namespace`, method / property / const declarations inside
  types, free `function_definition` at module level, top-level `const`
  as variable. 13 unit tests. Scheme `scip-php`.
- README (both languages) updated with 4 new subdirectory install
  commands and the expanded doctor table (10 indexers total: 1
  reference + 9 language plugins).
- End-to-end smoke fixture: 9 User-class files across Java / Go / Rust /
  TypeScript / Python / Swift / Kotlin / Ruby / PHP indexed in one
  `codemap index` pass — 24 symbols across 9 SCIP schemes, 0
  diagnostics, both bridges executed.

### Added — Java, Go, Rust independent PyPI plugins (2026-05-30)

- `plugins/codemap-java/` — Java indexer backed by `tree-sitter-java`.
  Captures class / interface / enum / record / method / constructor /
  field declarations, honours `package` declarations as `extra.package`,
  and walks nested types via a class stack. SCIP scheme `scip-java`.
  14 unit tests.
- `plugins/codemap-go/` — Go indexer backed by `tree-sitter-go`.
  Captures function / method (receiver-aware) / struct / interface /
  type / const / var declarations. `func (u *User) Login()` produces
  `scip-go . . . main.go/User#Login().` so both value and pointer
  receivers feed into the same `User#…` namespace. 13 unit tests.
- `plugins/codemap-rust/` — Rust indexer backed by `tree-sitter-rust`.
  Captures free functions, methods inside `impl` (both inherent and
  `impl Trait for Type`) attached to the impl'd type, trait method
  signatures attached to the trait, plus struct / enum / trait / const /
  static items. SCIP scheme `scip-rust`. 13 unit tests.
- Each plugin ships with its own `pyproject.toml`, `README.md`,
  `src/codemap_<lang>/`, and `tests/`, depends only on `codemap +
  tree-sitter-<lang>`, and registers its indexer through the
  `codemap.indexers` entry-point group — identical mechanism to the
  built-in Python indexer and the previously shipped
  `codemap-typescript` plugin.
- README (both English and Simplified Chinese) updated with subdirectory
  install commands for all four language plugins and the updated
  `codemap doctor` indexer table.
- End-to-end smoke test on a 5-language fixture (Java + Go + Rust + TS +
  Python User class): 13 symbols emitted across 5 schemes, all bridges
  ran successfully, 0 diagnostics.

### Added — TypeScript indexer as an independent PyPI plugin (2026-05-30)

- New `plugins/codemap-typescript/` package: a fully independent
  Python distribution implementing the `Indexer` Protocol for
  TypeScript / TSX. Backed by `tree-sitter-typescript`. Recognises
  `function_declaration`, `class_declaration`, `interface_declaration`,
  `method_definition`, module-level `lexical_declaration` (const/let),
  and `import_statement`. SCIP scheme `scip-typescript`.
- The plugin lives in its own directory with its own `pyproject.toml`,
  `README.md`, `src/codemap_typescript/`, and tests. It declares one
  entry-point — `codemap.indexers.typescript = codemap_typescript:Type
  ScriptIndexer` — and that single line is the only coupling to the host
  CodeMap repo. After `pip install -e plugins/codemap-typescript/`,
  `codemap doctor` lists `typescript` next to the built-in `python` and
  `_example_lang` indexers on **identical terms** (ADR-004 + ADR-L001).
- 14 plugin-local unit tests cover the indexer's symbol generation,
  scheme consistency, TSX support, syntax-error and invalid-UTF8
  diagnostics, and the nested-class case.
- New `docs/plugin-guide.md` walks third-party authors through the
  process step by step using the TypeScript plugin as the reference.
- End-to-end smoke test against a sample TS + TSX project: 9 symbols
  emitted across function / class / interface / method / variable
  kinds; both `.ts` and `.tsx` file patterns work.

### Added — Incremental + watch (2026-05-30)

- `codemap index --incremental` compares each file's sha256 against the
  previous `manifest.files` entry and only re-parses changed files. Deleted
  files are removed; new files are picked up. Bridges re-run from scratch
  on every incremental pass via a new `JsonStore.clear_bridge_outputs()`
  helper so cross-module aliases / routes always reflect the current state.
- `codemap index --watch` keeps the process alive, runs an initial
  (incremental) pass, and re-indexes after every batch of file-system
  events (debounced 500 ms). Requires the `watchdog` extra
  (`pip install codemap[watch]`); the runtime check exits 69 (`EX_UNAVAILABLE`)
  with a friendly install hint when watchdog is missing.
- Watch mode ignores events under `.codemap/` to avoid feedback loops on
  its own writes.
- 7 e2e tests cover the no-op fast path, modified / deleted / new files,
  bridge re-evaluation after a rename, fallback to full when no prior
  index exists, and a real subprocess-based watch test that proves the
  watcher reacts to a live file change.

### Added — Cross-module Python call resolution (2026-05-30)

- New `codemap.core.bridge.python_cross_module.PythonCrossModuleBridge`
  resolves the synthetic `scip-python . . . <module>/<leaf>.` targets the
  Python indexer emits for cross-file imports. The bridge looks for a
  local symbol with the matching leaf name; if the file stem also matches
  the last namespace segment of the synthetic target the alias confidence
  is `high`, otherwise it falls back to `medium` for unambiguous single
  candidates and bails on ambiguity.
- `JsonStore.callers` / `callees` now transparently expand aliases via a
  reverse-alias index built at load time, so query commands automatically
  see cross-module callers without the caller doing anything special.
- On the CodeMap repo itself, `callers SymbolID#` now finds 10 callers
  across http_route.py / _example_lang.py / python.py / test_symbol.py
  rather than just the 1 same-file reference visible before.
- 10 unit tests + 3 e2e tests cover happy paths (file-stem match,
  single-candidate by leaf), explicit skips (no candidates, ambiguous
  candidates, non-python scheme, non-call edges, already-resolved
  targets, dedup), and the multi-file callers behaviour through the CLI.

### Added — Diagnostics command + error UX (2026-05-30)

- New `codemap diagnostics` command lists diagnostics recorded during the
  last `codemap index`. Filters: `--severity` (error/warning/info),
  `--producer` (indexer or bridge name), `--code` (e.g. `ROUTE001`),
  `--limit`. Both human and JSON outputs.
- Indexer crashes mid-file now become an `INDEXER_CRASH` diagnostic
  instead of being buried in stderr. Bridge crashes become
  `BRIDGE_CRASH`. Unreadable source files become `IO001`. The run
  completes either way.
- `codemap index --dry-run` walks the project and reports the per-indexer
  file counts without writing `.codemap/`.
- Friendly CLI exception wrapper: unhandled exceptions print a short
  marked-up "Internal error" message with the issue tracker URL and exit
  70 (`EX_SOFTWARE`). Set `CODEMAP_FULL_TRACEBACK=1` for the full
  traceback.

### Added — Configuration file (2026-05-30)

- `.codemap/config.yaml` now actually loads, replacing the previous empty
  placeholder. Three layers are merged in order: built-in defaults →
  `~/.config/codemap/config.yaml` → `<project>/.codemap/config.yaml`.
  Recursive mapping merge means each layer only has to mention what it
  changes.
- New schema (`codemap.config.schema.Config`, pydantic-backed,
  `extra=forbid` so typos surface as errors):
  - `storage.backend` (`json` | `sqlite`)
  - `index.ignore` (glob patterns on both file names and project-relative
    paths), `index.max_file_bytes`, `index.follow_symlinks`
  - `indexers.enabled` / `indexers.disabled`
  - `bridges.enabled` / `bridges.disabled`
- `codemap index` honours every field — `ignore` filters the walk,
  `max_file_bytes` replaces the previously hard-coded limit, and
  enabled/disabled lists shape which indexers / bridges run.
- New `codemap config show [--project P]` command prints the merged
  configuration (rendered YAML + source paths or a JSON envelope) so it's
  obvious which layer contributed which value.
- Validation errors surface as `EX_CONFIG` (exit 78) with the offending
  field path, never as a stack trace.
- 15 unit tests + 10 e2e tests cover schema defaults, layer merging,
  YAML errors, validation errors, ignore / max_file_bytes / disabled
  indexers / disabled bridges in action. `docs/configuration.md`
  documents every key.

### Added — Python HTTP recognition + benchmark gate (2026-05-30)

- **Python indexer** now produces `http_route` and `http_calls` metadata
  for the `http_route` bridge to consume — meaning the cross-language
  pipeline works end-to-end on real Python projects, not just synthetic
  fixtures. Recognises FastAPI-style verb decorators (`@app.get("/x")`),
  Flask-style `@route("/x", methods=[...])`, and `requests` / `httpx` /
  `aiohttp` / `urllib3` client calls. URL-like heuristic (`/` or `http(s)://`)
  filters out incidental `dict.get("key")` calls. 17 new unit tests cover
  the matrix; 4 e2e tests prove `codemap routes` and `codemap callers`
  surface the linked client→server graph after a single `codemap index`.
- **Benchmark suite** (`tests/bench/`) with `pytest-benchmark`, gated behind
  the `bench` marker so the default `pytest` run is unaffected. Six
  measurements: full-index throughput, callers / callees / search / walk /
  shortest_path. Targets are documented in `docs/performance.md`.
- **ADR-010 (benchmark regression gate)** flipped from Proposed to
  **Accepted**. Current baseline on the CodeMap repo: full-index 73 ms /
  callers 4.7 µs / callees 26 µs / walk depth-10 72 µs — every target from
  design §21 cleared by orders of magnitude. `.github/workflows/bench.yml`
  runs the suite on every PR and fails the build on ≥ 20 % median
  regression vs. main.

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
