# ADR-002: Ship JSON storage in MVP; cut over to SQLite when scale demands

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §七 · ADR-003

## Context

The `.codemap/` directory must (a) be human-readable for debugging, (b)
support atomic writes, (c) scale to ≥100k symbols without locking up.

JSON is great for (a) and (b), poor for (c). SQLite + FTS5 is the inverse.
We do not want to commit to either at Day 1 — backend should be swappable.

## Decision

* Define a `SymbolStore` Protocol in `codemap.core.store`. Both backends
  implement it; everything outside `io/` depends on the Protocol only.
* Ship `JsonStore` first — fast to build, easy to debug, sufficient for
  Sprint 0 and the early-Sprint-N indexers.
* When any §21 scale/latency target is breached on a real project, promote
  `SqliteStore` (Sprint Y). Migrate via `codemap migrate --to sqlite`.

## Consequences

* **Pro**: business logic in `core/` is backend-agnostic from day one. The
  swap is one configuration line plus a `migrate` invocation.
* **Pro**: JSON is grep-able, diff-able, and round-trippable for tests.
* **Con**: maintain two backends once SQLite lands. Acceptable cost.
* **Con**: `JsonStore` loads everything into memory on `open()`. Tracking
  ticket: cut over before any monorepo with >50k symbols.

## References

* `src/codemap/core/store.py`
* `src/codemap/io/json_store.py`
* design §七.7 (SQLite schema, pre-allocated)
