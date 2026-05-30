# ADR-006: Enforce schema_version on every `.codemap/` load

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §6.1 · ADR-005

## Context

`.codemap/` JSON shapes will evolve. Without explicit versioning, a newer
CodeMap will silently load an older index and produce undefined behavior.

## Decision

* Every persisted JSON / SQLite manifest carries a `schema_version` semver.
* On `load_manifest`:
  * Missing or empty → reject (exit code 65).
  * Major mismatch → reject (exit code 65). User must run
    `codemap index --rebuild`.
  * Minor newer than ours → reject (we don't know future fields).
  * Minor older than ours → load + WARNING (we know we can read this).
  * Patch mismatch → silent.

## Consequences

* **Pro**: upgrades and downgrades are observable. No silent corruption.
* **Pro**: gives us a real lever to evolve the schema in MINOR bumps.
* **Con**: every breaking shape change costs a MAJOR bump and forces all
  users to rebuild. That cost is correct.

## References

* `src/codemap/io/manifest.py`
* `tests/unit/test_io.py::test_check_schema_version_*`
