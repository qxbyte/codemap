# ADR-010: Block PRs on >20% benchmark regression

* **Status**: Proposed
* **Date**: 2026-05-30
* **Related**: design §21

## Context

The system has explicit performance targets (§21): index time, query
latency P95, memory ceiling. Without enforcement, these targets rot — every
PR adds a little, and a year later nothing is fast.

## Decision (proposed; flipped to Accepted before Sprint 2)

* `tests/bench/` uses `pytest-benchmark` on a fixed set of reference open-
  source projects.
* CI runs benchmarks on every PR, posts a delta-vs-main comment.
* If any benchmark regresses by more than 20%, CI blocks merge. Author can
  override with an explanation + (optional) follow-up ticket.

Why "proposed" today: Sprint 0 has no indexer with realistic load. We will
accept after the first language Indexer lands (Sprint N-1) and a baseline
exists.

## Consequences

* **Pro**: regressions are caught at the diff-level, not by users.
* **Pro**: forces optimization decisions to be conscious.
* **Con**: flaky on shared CI runners. We mitigate by reporting a
  rolling-window median rather than a single sample.

## References

* `tests/bench/` (planned)
* `pyproject.toml` — `pytest-benchmark` listed in `[project.optional-dependencies]`
