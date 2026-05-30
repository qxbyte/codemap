# ADR-009: ruff + mypy --strict + import-linter + 80% coverage block CI

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §25.3

## Context

A platform that intends to ship third-party plugins and be embedded in MCP
clients cannot afford untyped, undisciplined, or accidentally-cyclic code.
Discipline imposed by reviewers does not scale.

## Decision

CI must pass, in order:

1. `ruff format --check .` (no diffs).
2. `ruff check .` (0 errors).
3. `mypy` (`--strict`, 0 errors).
4. `lint-imports` (all `import-linter` contracts in `pyproject.toml` kept).
5. `pytest --cov-fail-under=80` (all tests pass; coverage ≥ 80%).
6. `codemap index tests/fixtures/smoke` (smoke test — exit 0).

Every step is a hard PR block. The matrix runs across Python 3.11 / 3.12 /
3.13 × Linux / macOS.

## Consequences

* **Pro**: contributors get immediate, mechanical feedback on style, types,
  layering, and behavior.
* **Pro**: `import-linter` is the only mechanical enforcement of ADR-003.
* **Con**: PRs sometimes fail on stylistic noise — accepted cost.

## References

* `.github/workflows/test.yml`
* `pyproject.toml` `[tool.ruff]`, `[tool.mypy]`, `[tool.importlinter]`,
  `[tool.pytest.ini_options]`
