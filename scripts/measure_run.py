#!/usr/bin/env python3
"""measure_run.py — extract per-run metrics from task-swarm state.json.

Walk one or more ``<workdir>/.task-swarm/runs/*/state.json`` files and emit
a markdown table of metrics that matter for AI-EDS v1.0 evaluation:

- Run id / spec_id / status
- Wall-clock duration (started_at → completed_at)
- Group count + topology stats (needs / writes conflicts)
- Phase transition count (host attention proxy)
- Subagent fork count by role (coder / reviewer / validator) + p0-fix / v-fix
- Auto vs manual advance count (run-loop usage signal)
- Reviewer P0 抓出 count (quality signal)
- Validator pass/fail/round count (deadloop risk signal)
- Pipeline-end validator usage (M3 adoption signal)
- Auto-ingest case + pitfall count (knowledge production signal)
- Knowledge dir state snapshot (post-run, from project_root/.ai-memory/)

Usage::

    python3 scripts/measure_run.py <workdir-or-run-dir-or-state.json> [...]
    python3 scripts/measure_run.py --workdir /path/to/wework-ops-assistant
    python3 scripts/measure_run.py --workdir /path --format=json

Default ``--format=markdown`` emits one table per run; ``--format=json``
emits a list[dict] suitable for downstream A/B comparison scripts.

stdlib-only. No dependency on task-swarm internals — reads state.json schema
directly and tolerates missing fields (so older state.json from pre-0.8.0
runs still work, just with N/A for missing metrics).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _parse_iso(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _wall_clock_minutes(state: dict[str, Any]) -> float | None:
    """Return wall-clock minutes from started_at → completed_at (or last
    activity if not completed)."""
    started = _parse_iso(state.get("started_at"))
    if started is None:
        return None
    ended = _parse_iso(state.get("completed_at")) or _parse_iso(state.get("last_activity_at"))
    if ended is None:
        return None
    delta = ended - started
    return round(delta.total_seconds() / 60.0, 1)


def _count_events(events: list[dict], event_type: str, **filters: Any) -> int:
    """Count events of a given type matching all filters."""
    n = 0
    for e in events:
        if not isinstance(e, dict) or e.get("type") != event_type:
            continue
        if all(e.get(k) == v for k, v in filters.items()):
            n += 1
    return n


def _fork_count_by_role(events: list[dict]) -> dict[str, int]:
    """Estimate how many subagents were forked, by role.

    state.json doesn't directly log "fork" events — but it does log
    ``phase`` transitions to coding / review / p0-fix / validation / v-fix,
    one per group per round. We use those as a fork proxy.
    """
    out: Counter[str] = Counter()
    for e in events:
        if not isinstance(e, dict) or e.get("type") != "phase":
            continue
        phase = e.get("phase", "")
        # Phase transitions imply a fork (one or more subagents) of that role
        if phase in ("coding", "p0-fix", "v-fix"):
            out["coder"] += 1
        elif phase == "review":
            out["reviewer"] += 1
        elif phase == "validation":
            out["validator"] += 1
    return dict(out)


def _reviewer_p0_count(events: list[dict]) -> int:
    """Sum of evidence-tagged P0 items across all review advances."""
    return sum(
        e.get("p0", 0) or 0
        for e in events
        if isinstance(e, dict) and e.get("type") == "advance" and e.get("phase") == "review"
    )


def _validator_round_stats(events: list[dict]) -> dict[str, int]:
    """Per-group max validator round (deadloop proxy) + pass/fail counts."""
    pass_count = 0
    fail_count = 0
    max_round = 0
    for e in events:
        if not isinstance(e, dict) or e.get("type") != "advance":
            continue
        if e.get("phase") != "validation":
            continue
        verdict = e.get("verdict", "")
        if verdict == "pass":
            pass_count += 1
        elif verdict == "fail":
            fail_count += 1
        r = e.get("round", 0)
        if isinstance(r, int) and r > max_round:
            max_round = r
    return {"pass": pass_count, "fail": fail_count, "max_round": max_round}


def _ingest_stats(events: list[dict]) -> dict[str, int]:
    """Sum auto-ingested case + pitfall counts at resolve time."""
    cases = 0
    pits = 0
    for e in events:
        if not isinstance(e, dict) or e.get("type") != "ingest-lessons":
            continue
        cases += e.get("cases", 0) or 0
        pits += e.get("pitfalls", 0) or 0
    return {"cases": cases, "pitfalls": pits}


def _knowledge_snapshot(project_root: str | None) -> dict[str, int]:
    """Count current knowledge files under ``<project_root>/.ai-memory/knowledge/``.

    Run-time observation, not run-time event — but useful as accumulated
    'knowledge production' indicator across runs. Missing dir → all zeros.
    """
    out = {"rules": 0, "business": 0, "modules": 0, "cases": 0, "pitfalls": 0}
    if not project_root:
        return out
    base = Path(project_root) / ".ai-memory" / "knowledge"
    if not base.is_dir():
        return out
    for cat in out:
        d = base / cat
        if d.is_dir():
            out[cat] = sum(1 for f in d.iterdir() if f.is_file() and f.suffix == ".yml")
    return out


def measure_run(state_path: Path) -> dict[str, Any]:
    """Read one state.json and return a flat metric dict."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"path": str(state_path), "error": f"{type(exc).__name__}: {exc}"}

    events = state.get("events") or []
    groups = state.get("task_groups") or []

    fork_counts = _fork_count_by_role(events)
    validator_stats = _validator_round_stats(events)
    ingest = _ingest_stats(events)
    knowledge = _knowledge_snapshot(state.get("project_root"))

    return {
        "run_id": state.get("run_id", "?"),
        "spec_id": state.get("spec_id"),
        "status": state.get("failed_status"),
        "pipeline_end_status": state.get("pipeline_end_status", "n/a"),
        "wall_clock_min": _wall_clock_minutes(state),
        "groups": len(groups),
        "events_total": len(events),
        "phase_transitions": _count_events(events, "phase"),
        "fork_coder": fork_counts.get("coder", 0),
        "fork_reviewer": fork_counts.get("reviewer", 0),
        "fork_validator": fork_counts.get("validator", 0),
        "writeback_count": _count_events(events, "writeback"),
        "reviewer_p0_total": _reviewer_p0_count(events),
        "validator_pass": validator_stats["pass"],
        "validator_fail": validator_stats["fail"],
        "validator_max_round": validator_stats["max_round"],
        "pipeline_end_used": state.get("pipeline_end_validator", False),
        "ingest_cases": ingest["cases"],
        "ingest_pitfalls": ingest["pitfalls"],
        "knowledge_rules_now": knowledge["rules"],
        "knowledge_pitfalls_now": knowledge["pitfalls"],
        "knowledge_cases_now": knowledge["cases"],
        "knowledge_business_now": knowledge["business"],
        "knowledge_modules_now": knowledge["modules"],
        "project_root": state.get("project_root", ""),
        "path": str(state_path),
    }


def discover_state_files(targets: list[Path]) -> list[Path]:
    """Expand each target into one or more state.json paths.

    A target may be:
      - a state.json file → returned as-is
      - a run directory containing state.json → return state.json
      - a workdir containing .task-swarm/runs/*/state.json → return all
    """
    out: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path) -> None:
        rp = p.resolve()
        if rp in seen or not rp.is_file():
            return
        seen.add(rp)
        out.append(rp)

    for t in targets:
        if not t.exists():
            sys.stderr.write(f"measure_run: skip non-existent path: {t}\n")
            continue
        if t.is_file() and t.name == "state.json":
            _add(t)
            continue
        if t.is_dir():
            # Try the run-dir layout first
            cand = t / "state.json"
            if cand.is_file():
                _add(cand)
                continue
            # Try the workdir layout
            runs_dir = t / ".task-swarm" / "runs"
            if runs_dir.is_dir():
                for run in sorted(runs_dir.iterdir()):
                    sj = run / "state.json"
                    if sj.is_file():
                        _add(sj)
    return out


def render_markdown(metrics: list[dict[str, Any]]) -> str:
    """Emit a markdown table summarising N runs."""
    if not metrics:
        return "_(no runs found)_\n"

    # Use a wide set of columns; some users will prefer to grep / cut down.
    cols = [
        ("run_id", "run_id"),
        ("spec_id", "spec_id"),
        ("status", "status"),
        ("pipeline_end_status", "pe_status"),
        ("wall_clock_min", "wall(min)"),
        ("groups", "G"),
        ("phase_transitions", "phases"),
        ("fork_coder", "fork_c"),
        ("fork_reviewer", "fork_r"),
        ("fork_validator", "fork_v"),
        ("writeback_count", "wb"),
        ("reviewer_p0_total", "P0"),
        ("validator_pass", "v_pass"),
        ("validator_fail", "v_fail"),
        ("validator_max_round", "v_maxR"),
        ("pipeline_end_used", "pe"),
        ("ingest_cases", "ing_c"),
        ("ingest_pitfalls", "ing_p"),
        ("knowledge_rules_now", "kn_r"),
        ("knowledge_pitfalls_now", "kn_p"),
        ("knowledge_cases_now", "kn_c"),
    ]
    header = "| " + " | ".join(label for _, label in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    rows = [header, sep]
    for m in metrics:
        if "error" in m:
            rows.append(f"| _error: {m['error']}_ |" + " |" * (len(cols) - 1))
            continue
        cells = []
        for key, _ in cols:
            v = m.get(key, "")
            if v is None:
                v = "n/a"
            cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"


def render_aggregates(metrics: list[dict[str, Any]]) -> str:
    """One-line per-aggregate summary (means / sums across N runs)."""
    rows = [m for m in metrics if "error" not in m]
    if not rows:
        return ""

    n = len(rows)

    def _avg(key: str) -> float:
        vals = [m.get(key) for m in rows if isinstance(m.get(key), (int, float))]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    def _sum(key: str) -> int:
        return sum((m.get(key) or 0) for m in rows)

    out = [
        f"\n## Aggregate over {n} run(s)",
        "",
        f"- avg wall clock: {_avg('wall_clock_min')} min",
        f"- avg groups per run: {_avg('groups')}",
        f"- avg phase transitions per run: {_avg('phase_transitions')}",
        f"- total coder forks: {_sum('fork_coder')}",
        f"- total reviewer forks: {_sum('fork_reviewer')}",
        f"- total validator forks: {_sum('fork_validator')}",
        f"- total writebacks: {_sum('writeback_count')}",
        f"- total reviewer evidence-P0: {_sum('reviewer_p0_total')}",
        f"- total validator pass: {_sum('validator_pass')}",
        f"- total validator fail: {_sum('validator_fail')}",
        f"- max validator round seen: {max((m.get('validator_max_round') or 0) for m in rows)}",
        f"- runs using pipeline_end_validator: {_sum('pipeline_end_used')}",
        f"- total auto-ingested cases: {_sum('ingest_cases')}",
        f"- total auto-ingested pitfalls: {_sum('ingest_pitfalls')}",
    ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Extract task-swarm run metrics from state.json (AI-EDS v1.0 measurement tool)."
    )
    p.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="state.json files, run dirs, or workdirs (auto-discover .task-swarm/runs/)",
    )
    p.add_argument(
        "--workdir",
        type=Path,
        action="append",
        help="explicit workdir to scan (can be passed multiple times)",
    )
    p.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="output format (markdown table or json list)",
    )
    p.add_argument(
        "--no-aggregate",
        action="store_true",
        help="skip the aggregate summary section (markdown only)",
    )
    args = p.parse_args(argv)

    targets: list[Path] = list(args.targets or [])
    if args.workdir:
        targets.extend(args.workdir)
    if not targets:
        # Default: assume cwd is a workdir
        targets.append(Path.cwd())

    state_files = discover_state_files(targets)
    if not state_files:
        sys.stderr.write(
            f"measure_run: no state.json discovered under: {[str(t) for t in targets]}\n"
            "(pass --workdir /path/to/project, or a state.json file directly)\n"
        )
        return 1

    metrics = [measure_run(sj) for sj in state_files]
    # Sort by run_id (which embeds timestamp) ascending so trend is left-to-right
    metrics.sort(key=lambda m: m.get("run_id", ""))

    if args.format == "json":
        sys.stdout.write(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_markdown(metrics))
        if not args.no_aggregate:
            sys.stdout.write(render_aggregates(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
