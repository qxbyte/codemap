# Performance baseline

> This file holds the **current baseline measurements** the
> [ADR-010 regression gate](adr/0010-benchmark-regression.md) is anchored on.
> Numbers are produced by `pytest tests/bench -m bench`.

## Targets (from design §21)

| Metric | Target | Notes |
|---|---|---|
| Full index time | ≤ 60 s / 100 KLoC (single core, M-series) | Equivalent budget on the CodeMap repo (~5 KLoC): **≤ 3 s**. |
| Incremental index time | ≤ 2 s / single-file change | Not yet measured — needs `--incremental` (Sprint X). |
| Query P95: `callers` | ≤ 50 ms | |
| Query P95: `callees` | ≤ 50 ms | |
| Query P95: `trace` (depth 10) | ≤ 200 ms | |
| Memory peak | ≤ 1 GB at 100 k symbols (JSON backend) | Not yet measured at scale. |
| `.codemap/` size | ≤ 50 MB at 100 k symbols (JSON, no embeddings) | Not yet measured at scale. |

## Current baseline — CodeMap repository, single M-series core

Run: `pytest tests/bench -m bench -o addopts=""` against this commit on
the CodeMap source tree (48 files, ~5 KLoC, 437 symbols, 1232 edges).

| Bench | Median | Mean | Std dev | Ratio vs. target |
|---|---:|---:|---:|---:|
| `full_index_codemap_repo` | **72.8 ms** | 73.4 ms | 2.7 ms | **41× faster** than the 3 s budget |
| `callers` | **4.7 µs** | 4.7 µs | 1.0 µs | **10 600× faster** than the 50 ms budget |
| `callees` | **26.1 µs** | 26.5 µs | 2.2 µs | **1 880× faster** than the 50 ms budget |
| `walk_chain` depth 10 | **71.2 µs** | 72.1 µs | 4.5 µs | **2 770× faster** than the 200 ms budget |
| `shortest_path` (unreachable) | **10.4 µs** | 10.6 µs | 1.4 µs | (no explicit target) |
| `search` keyword | **1.49 ms** | 1.54 ms | 148 µs | (no explicit target) |

These figures vastly clear every published target — they exist to anchor
the regression gate (ADR-010), not to claim victory. A real test of the
upper limits requires a multi-100 KLoC project; that will land alongside
Sprint N-2 (the second language indexer).

## How to reproduce locally

```bash
pip install -e ".[dev]"
pytest tests/bench -m bench -o addopts=""
```

Tips:

* The `-o addopts=""` cancels the default `--cov` and `-m "not bench"`
  options from `pyproject.toml`. Without it, the bench suite is skipped.
* Add `--benchmark-save=NAME` to record a baseline; later runs can
  `--benchmark-compare=NAME` to delta against it.
* For an isolated, comparable run, drop background processes; benchmark
  variance dominates at the µs scale.

## Re-baselining policy (ADR-010)

* Improvements (lower numbers) update this table without ceremony.
* Regressions ≥ 20 % at the **median** of any baseline bench must either
  be explained in the PR description or rolled back. CI will surface the
  delta as a PR comment once `bench.yml` lands.
* A scale or architecture change (e.g. flipping JSON → SQLite) requires
  re-baselining all numbers, with both old and new figures captured in
  the changelog.

## Larger-project measurements (planned)

| Project | Size | Status |
|---|---|---|
| CodeMap itself | ~5 KLoC | Done — table above |
| `pydantic/pydantic` core/ | ~30 KLoC | Pending — pinned commit TBD |
| `tiangolo/fastapi` fastapi/ | ~20 KLoC | Pending |

These will be added once a stable harness for downloading and pinning
third-party sources exists in CI (out of scope for the initial Sprint).
