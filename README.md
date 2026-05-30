# CodeMap

> Language-neutral code index for AI agents — precise navigation without full-project search.

CodeMap builds a deterministic, AST-based index of your codebase so AI agents (Claude Code, Cursor, Codex, etc.) can find call chains, route mappings, and cross-file relationships without grepping the entire project. Indexing is static, fast, and reproducible — no LLM in the index path.

**Status**: Alpha (Sprint 0 — engineering scaffolding). Not yet usable.

## Core principles

1. **Static analysis first, LLM as consumer** — the index is deterministic and reproducible.
2. **Layered defense, confidence-graded** — admit uncertainty rather than hallucinate.
3. **Cross-asset bridging is the core value** — non-source assets (XML, YAML, IDL) bridge to code via the same protocol as languages.
4. **Evolvable path** — CLI → MCP Server → Agent CLI, each step independently valuable.
5. **Ecosystem-compatible** — SCIP for symbols, MCP for tools.
6. **Language-neutral** — no language or framework is privileged; all indexers and bridges register through the same plugin protocol (see ADR-L001).

## Quick start

```bash
# Install (when published)
pipx install codemap

# Dev install (current)
pip install -e ".[dev]"

# Use
cd my-project
codemap index
codemap doctor
codemap --help
```

## Architecture overview

```
cli  →  core  ←  indexers
        ↑          ↑
        └── io ────┘
        ↑
        mcp
```

- **core**: pure business logic, Pydantic models, SymbolID (SCIP), call-graph algorithms
- **io**: persistence adapters (JSON now, SQLite when scale demands)
- **indexers**: pluggable language/asset indexers (entry_points)
- **bridges**: pluggable cross-language resolvers (entry_points)
- **cli**: Typer surface, output rendering
- **mcp**: MCP server (later sprint)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New language? Implement the `Indexer` Protocol and register an entry_point — main repo will not privilege any language.

## License

MIT — see [`LICENSE`](LICENSE).
