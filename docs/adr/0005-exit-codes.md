# ADR-005: Use sysexits.h exit codes

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §22.1

## Context

CI scripts, post-commit hooks, and MCP servers all need to branch on
specific CodeMap failure modes (corrupted index vs. lock timeout vs. no
input). Parsing stderr is brittle.

## Decision

Adopt a subset of BSD `sysexits.h`. Codes are defined once in
`codemap.diagnostics.exit_codes.ExitCode` and used consistently across
commands.

| Code | Symbol | Meaning |
|---|---|---|
| 64 | `EX_USAGE` | bad command-line arguments |
| 65 | `EX_DATAERR` | corrupt index, incompatible schema |
| 66 | `EX_NOINPUT` | `.codemap/` missing |
| 70 | `EX_SOFTWARE` | internal bug |
| 73 | `EX_CANTCREAT` | write failed |
| 75 | `EX_TEMPFAIL` | lock contention timeout |

## Consequences

* **Pro**: callers can match on stable, documented numbers.
* **Pro**: well-known convention — script authors don't have to learn ours.
* **Implication**: any new failure mode lands here first, then in commands.

## References

* `man sysexits`
* `src/codemap/diagnostics/exit_codes.py`
