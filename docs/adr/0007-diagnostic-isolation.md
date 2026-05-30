# ADR-007: Isolate per-file indexer exceptions; report as Diagnostic

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §22.2

## Context

If one malformed source file crashes an indexer, the whole `codemap index`
run aborts and the user loses progress on the other 9 999 files. That is a
terrible UX.

## Decision

The orchestration layer wraps every `Indexer.index_file` call in a
try/except. On exception, the indexer's failure becomes a
`Diagnostic(severity="error", code=..., producer=...)` entry in
`diagnostics.json`. Indexing continues with the next file.

The same rule applies to bridges via `try/except` around `Bridge.resolve`.

## Consequences

* **Pro**: a single bad file no longer poisons the index.
* **Pro**: `codemap doctor` surfaces collected diagnostics so users can
  triage offending files.
* **Con**: indexer authors might miss real bugs hidden inside diagnostics.
  Mitigated by logging at WARNING and by the doctor command.

## References

* `src/codemap/cli/commands/index.py`
* `codemap.core.models.Diagnostic`
