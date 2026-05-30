# ADR-001: Adopt SCIP Symbol format for cross-language SymbolID

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §五 (Symbol ID 规范) · ADR-L001

## Context

A code index needs one identifier per symbol that is stable across languages,
file types, and assets. The decision is foundational: every persisted JSON
key, every Bridge alias, every MCP tool argument is keyed on this ID. Wrong
choice = forced data migration later.

Two natural candidates:

1. A path-style ID like `src/foo.py::Class.method`.
2. The SCIP Symbol grammar from Sourcegraph (`scip.proto`).

## Decision

Use the SCIP Symbol grammar. All schemes — built-in source languages
(`scip-python`, `scip-go`, ...), built-in assets (`scip-sqlmap`,
`scip-template`, ...), and custom bridge intermediates (`scip-route`, ...) —
register and are stored as plain strings under the same encoding.

## Consequences

* **Pro**: interoperate with any `scip-*` indexer the Sourcegraph ecosystem
  ships. We can consume their output as input.
* **Pro**: the scheme prefix is open; new languages or asset types are added
  by picking a new identifier, no schema migration.
* **Pro**: backtick-escaping handles arbitrary characters (slashes, spaces,
  unicode), so file names and URL paths can be embedded inline.
* **Con**: a non-trivial parser must be implemented and maintained. We did so
  in `codemap.core.symbol`, with round-trip tests on every supported scheme.
* **Implication**: ADR-L001 — schemes are equal citizens. The parser and
  storage make no scheme-specific decisions.

## References

* [Sourcegraph SCIP](https://github.com/sourcegraph/scip)
* `src/codemap/core/symbol.py`
* `tests/unit/test_symbol.py`
