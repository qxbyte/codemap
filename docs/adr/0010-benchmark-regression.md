# ADR-010: Block PRs on >20% benchmark regression at the median

* **Status**: Accepted (2026-05-30; was Proposed at Sprint 0)
* **Date**: 2026-05-30
* **Related**: design §21 · `docs/performance.md`

## Context

The system has explicit performance targets (§21): index time, query
latency P95, memory ceiling. Without enforcement, these targets rot — every
PR adds a little, and a year later nothing is fast.

This ADR was Proposed at Sprint 0 because no real-language indexer existed,
so there was no realistic load to baseline against. Sprint N-1 shipped the
Python indexer; this ADR can now move to Accepted.

## Decision

* `tests/bench/` uses `pytest-benchmark` against the CodeMap repository
  itself as the canonical subject (more projects will be added once the
  CI harness can pin third-party sources — see `docs/performance.md`).
* Bench tests are marked `@pytest.mark.bench` and excluded from the default
  `pytest` invocation; `pytest -m bench -o addopts=""` opts in.
* The baseline numbers live in `docs/performance.md`, anchored to a specific
  commit. They are updated when an improvement is intentional.
* The `bench` CI job (`.github/workflows/bench.yml`) runs the bench suite on
  every PR and posts a delta-vs-main comment.
* A regression ≥ 20 % at the **median** of any tracked bench is treated as a
  PR-blocking event: the author must either explain it in the PR
  description (the gate then becomes informational for that PR) or fix
  it. Median is used rather than mean to dampen single-sample variance
  on shared CI runners.

## Consequences

* **Pro**: regressions are caught at the diff-level, not by users.
* **Pro**: forces optimisation decisions to be conscious — even a 21 %
  slowdown requires an explicit justification in the PR.
* **Pro**: the baseline doc serves as ongoing documentation of what the
  system can actually do — useful for issue triage.
* **Con**: flaky on shared CI runners. Mitigations: (a) median, not mean;
  (b) `pytest-benchmark`'s `--benchmark-compare-fail` honours a tolerance
  band; (c) the job runs each bench with multiple rounds so a single
  unlucky sample doesn't blow up.
* **Con**: small refactors that incidentally slow a hot path must update
  the baseline doc. Acceptable.

## Current baseline (this commit)

See `docs/performance.md` — every published target is currently cleared
by a multiple-orders-of-magnitude margin. The gate's purpose is to stop
that margin from silently shrinking.

## References

* `tests/bench/test_index_perf.py`, `tests/bench/test_query_perf.py`
* `docs/performance.md`
* `.github/workflows/bench.yml`
