# Changelog

All notable changes to CodeMap will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, MINOR may introduce breaking changes — they will be marked `BREAKING:`.

## [Unreleased]

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
