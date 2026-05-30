# Changelog

All notable changes to CodeMap will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, MINOR may introduce breaking changes — they will be marked `BREAKING:`.

## [Unreleased]

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
