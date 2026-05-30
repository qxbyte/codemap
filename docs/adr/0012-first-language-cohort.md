# ADR-011: First-cohort language list is engineering-convenience, not strategy

* **Status**: Proposed
* **Date**: 2026-05-30
* **Related**: ADR-L001 · design §三十二

## Context

Sprint 0 builds infrastructure. Sprint N then begins with one — and only
one — Indexer that exercises the platform end-to-end on a real codebase.
The choice of *which* language must not signal product preference (ADR-L001).

## Decision (proposed)

* Sprint N-1 ships a Python Indexer. The reasons are purely engineering:
  * The CLI itself is Python, so this is dogfooding.
  * Python's stdlib `ast` module is zero-dependency, fast, and trivially
    correct. We do not have to make a tree-sitter / language-parser pick
    yet.
* Sprint N-2, N-3, ... pick based on a public evaluation rubric:
  * AST tooling maturity (tree-sitter coverage, official parser, ...).
  * Representative open-source projects available for benchmarks.
  * Bridge complexity (does the ecosystem need a meaningful Bridge to
    show value, or just an Indexer?).
  * Community pull (issues, requests, third-party offers).
* The rubric is documented in `docs/indexers/_evaluation.md` and applied
  identically to every candidate.

## Consequences

* **Pro**: language choices are visibly principled, not arbitrary.
* **Pro**: dogfooding Python first uncovers Sprint 0 contract bugs early.
* **Con**: an unsuccessful early Indexer might mistakenly be read as
  product commitment. Mitigated by ADR-L001's explicit disclaimer in
  every release note that mentions a specific language.

## References

* design §三十二 (Sprint N template)
* ADR-L001
