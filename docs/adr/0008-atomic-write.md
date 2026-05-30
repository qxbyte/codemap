# ADR-008: All `.codemap/` writes use tmp + rename + fsync

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §19.1, §19.2 · ADR-002

## Context

A crash mid-write — power loss, signal, kill -9 — must not leave
`symbols.json` half-written. POSIX `rename(2)` is atomic; raw `open(...,
"w")` is not.

## Decision

* `codemap.io.atomic.atomic_write` writes to `<name>.tmp.<pid>`, fsyncs,
  then `os.replace`s onto the target. On exception, the tmp is removed.
* `codemap.io.lock.file_lock` holds an exclusive `flock` on `.codemap/.lock`
  during any write transaction. Lock cookie includes PID + ISO timestamp
  so users can investigate stale locks.
* At startup, `sweep_stale_tmp_files` removes any `*.tmp.<pid>` whose pid
  is no longer running (and that is old enough not to belong to a
  concurrent process).

## Consequences

* **Pro**: index files are always in a valid state on disk. There is no
  partial-write recovery code.
* **Pro**: two processes never corrupt one index — the second fails with
  exit code 75 (`EX_TEMPFAIL`) instead.
* **Con**: tiny overhead per write (an extra rename + fsync). Negligible.

## References

* `src/codemap/io/atomic.py`
* `src/codemap/io/lock.py`
* `tests/unit/test_io.py::test_atomic_write_*`,
  `test_file_lock_times_out_when_held`
