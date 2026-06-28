# scripts/

Repo-level utility scripts. stdlib-only by convention so they run from any
checkout without `uv sync` / `pip install`.

## measure_run.py

Extract per-run metrics from one or more task-swarm `state.json` files —
for AI-EDS v1.0 evaluation (cross-round comparison, baseline A/B, knowledge
production trend).

Usage:

```bash
# Scan all runs under a wework-ops-assistant-like workdir
python3 scripts/measure_run.py --workdir /path/to/project

# Scan a specific run dir
python3 scripts/measure_run.py /path/to/project/.task-swarm/runs/20260628-xxx

# Compare multiple workdirs (e.g. with-engine vs baseline-only A/B)
python3 scripts/measure_run.py --workdir /path/A --workdir /path/B

# Machine-readable output for downstream A/B analysis
python3 scripts/measure_run.py --workdir /path --format=json
```

Metrics emitted (per run):

| Column | Meaning |
|---|---|
| `wall(min)` | started_at -> completed_at minutes |
| `G` | task_group count |
| `phases` | phase transitions (host attention proxy) |
| `fork_c/r/v` | coder / reviewer / validator subagent forks |
| `wb` | writeback count |
| `P0` | reviewer evidence-tagged P0 total caught (quality signal) |
| `v_pass/fail/maxR` | validator pass / fail / max round (deadloop risk) |
| `pe` | pipeline_end_validator used (M3 adoption) |
| `ing_c/p` | auto-ingested case / pitfall count |
| `kn_r/p/c` | current knowledge snapshot (post-run) |

Aggregate summary follows the per-run table (avg / sum across N runs).

stdlib-only, no codemap-internal imports — works on state.json from any
task-swarm version that includes the v0.8.x schema (older state.json with
missing fields gracefully degrade to `n/a`).
