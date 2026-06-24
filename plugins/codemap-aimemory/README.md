# codemap-aimemory

Emits the [four-layer memory model](https://github.com/qxbyte/codemap)'s
L1 (`.ai-memory/`) output from a CodeMap index.

## What it writes

```
.ai-memory/
├── entities/
│   ├── functions.yml       fn-* / cls-* entities, with calls / called_by /
│   │                       related_tables / signature / line_range
│   ├── tables.yml          tbl-* entities
│   └── files.yml           file-* entities
├── relations/
│   ├── call-graph.yml      from / to / type=calls / confidence
│   ├── table-relations.yml from / to / type=accesses_table / confidence
│   └── rule-constraints.yml (empty; managed by L2)
└── enrichment/             optional LLM overlay (one file per enriched
                            symbol, loaded by the emitter to fill
                            business_meaning / related_rules)
```

All writes are atomic per file (tmp + rename), so an Agent reading
`.ai-memory/` never sees a half-written tree.

## Two-layer separation

The core L1 output (above) is purely deterministic — no LLM. The optional
`enrich` CLI fills `business_meaning` / `related_rules` into separate
`enrichment/*.yml` files. The emitter merges enrichment values when it
re-emits, but the core JSON-store index never carries explanation text.
