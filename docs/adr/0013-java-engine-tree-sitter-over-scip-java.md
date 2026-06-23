# ADR-0013: Java engine — tree-sitter over scip-java

* **Status**: Accepted
* **Date**: 2026-06-24
* **Related**: design `2026-06-23-codemap-l1-知识图谱重构-design.md` §A1/§B1 · spike `2026-06-23-scip-java-findings.md` · ADR-0004 (indexer/bridge plugin) · ADR-0007 (diagnostic isolation) · ADR-L001 (language neutrality)

## Context

The original L1 knowledge-graph design (2026-06-23) picked scip-java as Java's
semantic backend, citing maximum precision (interface→impl, overloads,
generics, cross-file resolution). Implementing it required:

* ~100 MB scip-java + coursier + JVM toolchain on the user's machine
* The target project must be `mvn`/`gradle` buildable (private-repo deps, JDK
  pinning, multi-module)
* protoc / grpcio-tools to vendor `scip_pb2.py`
* A spike (Plan 0) to confirm the real SCIP symbol string format before
  Plan 2's `symbol_map` / `extract_edges` could be written
* `mvn compile` on every full index — minute-scale, doesn't fit watch mode

The user explicitly rejected this weight tradeoff in favor of a lighter
default engine that still meets the spec's "high precision call graph"
ambition for the common path.

## Decision

**Use tree-sitter-java as the sole Java engine.** Permanently drop scip-java.

The architecture stays the same — declarations come from a per-file
`JavaIndexer`, cross-file edges (calls/extends/implements) come from a
separate resolver — but the resolver runs in Python on tree-sitter AST plus
an import + FQN graph it builds itself, not on a `.scip` file.

Implementation shape:

1. **`JavaIndexer` (per-file, existing — extended)**: in addition to today's
   declarations, capture `import` statements and method invocations into
   `Symbol.extra["pending_calls"]` (raw records: receiver name, method name,
   argument arity, location).
2. **`JavaCallResolverBridge` (new, runs in the bridge phase)**: read all
   Java symbols + their pending_calls, build a project-wide FQN table from
   the import statements, same-package declarations, and explicit
   `extends`/`implements` relations, then emit `calls` / `extends` /
   `implements` / `overrides` edges with `confidence: medium`.
3. **Spring annotations + http_route metadata** stay in the indexer (Plan 3
   Task 1/2) using tree-sitter — no scip-java needed for that anyway.
4. **MyBatis** (Plan 3 Task 3) rebuilds the Java method `SymbolID` using the
   codemap-java scheme (consistent with the new indexer), not the scip-java
   symbol format. This removes the spike-Plan-0 dependency entirely.

### Alternatives considered

* **B — Hybrid (tree-sitter default + scip-java optional)**: tempting but
  doubles the implementation surface and forces every downstream consumer
  to handle two backends with different fidelity.
* **C — Bytecode parsing (javap / asm)**: still requires `mvn compile`, so it
  inherits scip-java's "your project must build" weight. Python bytecode-
  parsing ecosystem is thinner than tree-sitter.

## Consequences

What becomes easier:

* Zero external Java toolchain. `pip install codemap-core codemap-java`
  works out of the box on any machine.
* No spike unblock required. Plan 2 can start TDD immediately.
* Watch mode and incremental indexing become realistic (per-file tree-sitter
  parse is millisecond-scale).
* Plan 4's Golden test fixture no longer needs scip-java in CI.

What becomes harder / what we accept:

* **Precision ceiling drops from "high" to "medium" for `calls` edges.**
  Realistic targets on Spring/MyBatis projects:
  * `calls`: 70–80% precision (overload disambiguation by arity only; dynamic
    dispatch through interface-typed fields resolved heuristically by
    DI-known impls — see follow-up below)
  * `implements`/`extends`: ~95% (explicit `implements X, Y` syntax)
  * Annotation extraction: 100% (purely syntactic)
* Reflection, dynamic proxies, and Spring AOP-style indirection produce
  edges that look correct syntactically but miss runtime targets. These are
  the same blind spots tree-sitter has anywhere; we mark them with `medium`
  confidence rather than pretend.
* The precision gate (Plan 4 Task 5) lowers its `high`-tier threshold,
  effectively becoming a `medium`-tier `≥ 0.70` gate on `calls` and a
  `≥ 0.95` gate on `implements`/`extends`. Regression-detection rationale
  unchanged.

What we keep paying for:

* The FQN resolver is real code we own — when Java's grammar changes (new
  language features, pattern-matching) tree-sitter-java updates flow
  through, but our resolver has to keep up too.
* The `ProjectIndexer` protocol added in Plan 1 Task 2 is retained as a
  generic extension point for future heavier engines (e.g. someone wants to
  ship a scip-java backend later) — Java itself no longer uses it, but
  emptying the slot would break the symmetry with `Indexer`/`Emitter`.

Follow-up ADRs / decisions:

* If/when a project demonstrates that medium precision is insufficient (e.g.
  precision-gate alarms repeatedly), revisit and consider adding scip-java
  as an *opt-in* second backend that publishes the same SymbolID shape — at
  that point Hybrid (alternative B) becomes a focused upgrade rather than
  default complexity.

## References

* spec `2026-06-23-codemap-l1-知识图谱重构-design.md` (Obsidian vault) §A1/§B1
* spike `docs/spikes/2026-06-23-scip-java-findings.md` §0 (toolchain blocker
  that triggered the rethink)
* `docs/adr/0004-indexer-bridge-plugin.md` (resolver lives as a bridge, not a
  new plugin layer)
* `docs/adr/0007-diagnostic-isolation.md` (unresolved calls become
  diagnostics, never crashes)
