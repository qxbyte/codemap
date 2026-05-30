# ADR-003: Split the package into `core` / `io` / `indexers` / `cli` / `mcp`

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §四 · ADR-009

## Context

The MCP server (Sprint X) will call the same logic the CLI does. If the CLI
encapsulates business logic, MCP becomes a subprocess shell — slow and
fragile. The split must be in place before any business logic lands.

## Decision

The dependency graph is enforced one-way: `cli → core ← indexers`,
`cli → core ← io`, `mcp → core`. `core` defines Protocols; outer layers
implement them. `import-linter` contracts in `pyproject.toml` block any PR
that violates the direction.

## Consequences

* **Pro**: MCP server (Sprint X) calls `codemap.core.Project` directly —
  no subprocess overhead, no JSON parsing of CLI output.
* **Pro**: each layer is independently testable. Bridges accept a Protocol,
  not a backend — tests pass synthetic stores.
* **Con**: more files and more `__init__.py` ceremony than a one-module CLI.
  Acceptable.

## References

* `src/codemap/core/`
* `pyproject.toml` `[tool.importlinter]`
