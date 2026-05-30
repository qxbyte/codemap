# ADR-L001: Language neutrality is non-negotiable

* **Status**: Accepted
* **Date**: 2026-05-30
* **Related**: design §三 · ADR-001 · ADR-004 · ADR-011

## Context

When a code-index platform privileges a particular language or framework,
its data model, plugin protocol, and documentation acquire that language's
shape. New languages then have to fight the shape to join.

The temptation is real: every example in a design document picks *some*
language, and any specific language ecosystem has a vocal community willing
to subsidize "first-class" treatment. We've seen this play out in other
platforms; the result is a one-language platform with vestigial multi-
language hooks.

## Decision

**No specific language, framework, or ecosystem is a first-class citizen.**
All of the following are bound by this rule:

* Product positioning, README, marketing.
* Roadmap priority. Sprint N is a *template*, not "Sprint 2 = Java".
* Architecture documents, ADRs, code comments.
* The SCIP scheme registry (ADR-001) and the indexer / bridge registries
  (ADR-004): every scheme registers through the same door.
* The main repository ships only `_example_lang` as a reference Indexer.
  Real-language Indexers live in plugin packages on equal footing.

Specific language names appearing in design / docs are **architecture
illustrations** ("for example, a Python indexer could ..."), never product
commitments.

## Consequences

* **Pro**: third parties trust that their language is treated identically.
* **Pro**: the data model and protocols never accumulate language-specific
  hacks.
* **Con**: marketing has to work harder — "language-neutral code index" is
  abstract. Mitigated by concrete demo projects across multiple languages.
* **Implication**: ADR-011 — the first-cohort language list is an
  *engineering convenience* judgment (AST tooling maturity, dogfooding),
  never a product strategy.

## References

* design §三 L-001
* design §三十 (roadmap framing)
