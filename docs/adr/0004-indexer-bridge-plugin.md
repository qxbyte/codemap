# ADR-004: Indexers and bridges register via entry_points; no built-in privilege

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §4.3 · ADR-L001

## Context

A code-index platform that wants language neutrality cannot have a hard-coded
list of supported languages in `cli.py`. Every new language must enter the
system through the same door.

## Decision

* `Indexer` and `Bridge` are runtime-checkable Protocols defined in `core`.
* Both are discovered via Python `entry_points`:
  `[project.entry-points."codemap.indexers"]` and `"codemap.bridges"`.
* The reference `_example_lang` indexer ships in this repository, registered
  through the same entry-point group as any third-party indexer. It exists
  to exercise the pipeline, not to claim a built-in seat.

## Consequences

* **Pro**: adding a language is a separate package, no PR against this repo
  required.
* **Pro**: the registry is identical for built-in and third-party; we cannot
  accidentally regress to a hard-coded list.
* **Con**: failed plugin loads must be handled gracefully (logged, not
  crashed). The registry does so.

## References

* `src/codemap/indexers/registry.py`
* `src/codemap/core/bridge/registry.py`
* `CONTRIBUTING.md` — "Adding a new Indexer / Bridge"
