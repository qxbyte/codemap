# CodeMap

**English** · [简体中文](./README.zh-CN.md)

> Language-neutral code index for AI agents — precise navigation without
> full-project search.

CodeMap builds a deterministic, AST-based index of your codebase so AI
agents (Claude Code, Cursor, Codex, etc.) can find call chains, route
mappings, and cross-file relationships without grepping the entire
project. Indexing is static, fast, and reproducible — no LLM in the
index path.

**Status**: Alpha. The CLI is usable today; PyPI release is not yet
published, so install directly from this repository.

---

## Table of contents

- [Core principles](#core-principles)
- [Installation](#installation)
  - [1. Main CLI](#1-main-cli)
  - [2. Optional extras](#2-optional-extras)
  - [3. TypeScript plugin (subdirectory)](#3-typescript-plugin-subdirectory)
  - [4. Local clone (development)](#4-local-clone-development)
  - [5. System requirements](#5-system-requirements)
- [Verify](#verify)
- [Commands](#commands)
- [Configuration](#configuration)
- [Built-in indexers and bridges](#built-in-indexers-and-bridges)
- [Architecture](#architecture)
- [Writing a plugin](#writing-a-plugin)
- [Performance](#performance)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Core principles

1. **Static analysis first, LLM as consumer** — the index is
   deterministic and reproducible.
2. **Layered defense, confidence-graded** — admit uncertainty rather
   than hallucinate.
3. **Cross-asset bridging is the core value** — non-source assets (XML,
   YAML, IDL) bridge to code via the same protocol as languages.
4. **Evolvable path** — CLI → MCP Server → Agent CLI, each step
   independently valuable.
5. **Ecosystem-compatible** — SCIP for symbols, MCP for tools.
6. **Language-neutral** — no language or framework is privileged; all
   indexers and bridges register through the same plugin protocol
   (see [ADR-L001](docs/adr/0011-language-neutrality.md)).

## Installation

### 1. Main CLI

```bash
# Easiest: install from main branch
pip install git+https://github.com/qxbyte/codemap.git

# Recommended: pipx provides environment isolation + a system-wide
# `codemap` command
pipx install git+https://github.com/qxbyte/codemap.git

# Or with uv
uv tool install git+https://github.com/qxbyte/codemap.git

# Pin to a specific commit / tag for reproducible installs
pip install git+https://github.com/qxbyte/codemap.git@main
pip install git+https://github.com/qxbyte/codemap.git@2c3ed45
```

### 2. Optional extras

```bash
# `--watch` mode needs watchdog
pip install "codemap[watch] @ git+https://github.com/qxbyte/codemap.git"

# Development tools (tests, lint, mypy, import-linter, benchmarks)
pip install "codemap[dev] @ git+https://github.com/qxbyte/codemap.git"

# pipx form (note the `#egg=` syntax)
pipx install "git+https://github.com/qxbyte/codemap.git#egg=codemap[watch]"
```

### 3. Language plugins (subdirectory installs)

Each non-Python language indexer is shipped as an **independent PyPI
package** under `plugins/`. GitHub installs of a subdirectory use the
`subdirectory=...` URL fragment:

```bash
# TypeScript / TSX
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-typescript"

# Java
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"

# Go
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-go"

# Rust
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-rust"

# Swift
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-swift"

# Kotlin
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-kotlin"

# Ruby
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-ruby"

# PHP
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-php"

# SQL (DDL)
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-sql"

# Bash / shell scripts
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-bash"
```

Each plugin declares `codemap` as a dependency, so pip will pull the
main package if you don't already have it. After installation, `codemap
doctor` lists every installed plugin alongside the built-in indexers on
identical terms — see [Writing a plugin](#writing-a-plugin) for the
design.

### 4. Local clone (development)

```bash
git clone https://github.com/qxbyte/codemap.git
cd codemap

# Editable install with all dev tooling
pip install -e ".[dev,watch]"

# Optionally install language plugins in editable mode
pip install -e plugins/codemap-typescript
pip install -e plugins/codemap-java
pip install -e plugins/codemap-go
pip install -e plugins/codemap-rust
pip install -e plugins/codemap-swift
pip install -e plugins/codemap-kotlin
pip install -e plugins/codemap-ruby
pip install -e plugins/codemap-php
pip install -e plugins/codemap-sql
pip install -e plugins/codemap-bash
```

### 5. System requirements

| Item | Requirement |
|---|---|
| Python | ≥ 3.11 (the project develops on 3.13) |
| OS | macOS / Linux (Windows may need polling fallback for `--watch`) |
| Network | Required at install time to fetch `tree-sitter-typescript` etc. |

---

## Verify

```bash
codemap --version      # → 0.1.0
codemap --help         # list global flags + subcommands
codemap doctor         # show registered indexers, bridges, and `.codemap/` state
```

A successful install with the TypeScript plugin should look like:

```
$ codemap doctor
CodeMap 0.1.0
project_root: /your/path

                   Registered indexers
┃ name          ┃ version ┃ languages  ┃ file_patterns ┃
┃ _example_lang │ 0.1.0   │ example    │ *.example     │
┃ python        │ 0.1.0   │ python     │ *.py, *.pyi   │
┃ typescript    │ 0.1.0   │ typescript │ *.ts, *.tsx   │
┃ java          │ 0.1.0   │ java       │ *.java        │
┃ go            │ 0.1.0   │ go         │ *.go          │
┃ rust          │ 0.1.0   │ rust       │ *.rs          │
┃ swift         │ 0.1.0   │ swift      │ *.swift       │
┃ kotlin        │ 0.1.0   │ kotlin     │ *.kt, *.kts   │
┃ ruby          │ 0.1.0   │ ruby       │ *.rb          │
┃ php           │ 0.1.0   │ php        │ *.php         │
┃ sql           │ 0.1.0   │ sql        │ *.sql, *.ddl  │
┃ bash          │ 0.1.0   │ bash       │ *.sh, *.bash, *.bats │

           Registered bridges
┃ name                 ┃ version ┃ requires ┃
┃ http_route           │ 0.1.0   │ -        │
┃ python_cross_module  │ 0.1.0   │ -        │
```

---

## Commands

Full reference: [`docs/cli.md`](docs/cli.md).

```bash
# Index a project (writes .codemap/)
codemap index /path/to/project
codemap index . --rebuild               # discard old index
codemap index . --incremental           # re-parse only files whose sha256 changed
codemap index . --watch                 # stay running and re-index on changes
codemap index . --dry-run               # report what would be indexed, no write

# Diagnose
codemap doctor                          # plugins + index health
codemap diagnostics --severity error    # show recorded warnings / errors
codemap config show                     # merged effective configuration

# Query
codemap search login -n 5
codemap get '<symbol-id>'
codemap callers '<symbol-id>' --depth 2
codemap callees '<symbol-id>'
codemap trace --from '<id>' --depth 5
codemap trace --from '<id>' --to '<id>' # shortest path
codemap routes                          # HTTP routes from the http_route bridge

# Machine-readable output: all commands take --json
codemap --json callers '<symbol-id>'
```

Exit codes follow `sysexits.h` (ADR-005); see
[`docs/cli.md`](docs/cli.md#exit-codes) for the table.

---

## Configuration

Project-level configuration lives at `.codemap/config.yaml` (committed
or git-ignored — your choice). A user-level override at
`~/.config/codemap/config.yaml` is layered on top of built-in defaults,
and the project file is layered on top of that. CLI flags win over all
three.

```yaml
# .codemap/config.yaml
storage:
  backend: json          # json | sqlite (sqlite reserved for a future sprint)

index:
  ignore: []             # extra fnmatch patterns on names + project-relative paths
  max_file_bytes: 10485760
  follow_symlinks: false

indexers:
  enabled: all           # "all" or an explicit list of indexer names
  disabled: []           # subtractive

bridges:
  enabled: all
  disabled: []
```

Full reference: [`docs/configuration.md`](docs/configuration.md).
Run `codemap config show` to inspect the merged result and see which
file contributed each value.

---

## Built-in indexers and bridges

| Indexer | Files | Provided by | Status |
|---|---|---|---|
| `python` | `*.py`, `*.pyi` | main repo | first-class, dogfooded |
| `typescript` | `*.ts`, `*.tsx` | [`plugins/codemap-typescript/`](plugins/codemap-typescript) | independent plugin |
| `java` | `*.java` | [`plugins/codemap-java/`](plugins/codemap-java) | independent plugin |
| `go` | `*.go` | [`plugins/codemap-go/`](plugins/codemap-go) | independent plugin |
| `rust` | `*.rs` | [`plugins/codemap-rust/`](plugins/codemap-rust) | independent plugin |
| `swift` | `*.swift` | [`plugins/codemap-swift/`](plugins/codemap-swift) | independent plugin |
| `kotlin` | `*.kt`, `*.kts` | [`plugins/codemap-kotlin/`](plugins/codemap-kotlin) | independent plugin |
| `ruby` | `*.rb` | [`plugins/codemap-ruby/`](plugins/codemap-ruby) | independent plugin |
| `php` | `*.php` | [`plugins/codemap-php/`](plugins/codemap-php) | independent plugin |
| `sql` | `*.sql`, `*.ddl` | [`plugins/codemap-sql/`](plugins/codemap-sql) | independent plugin (DDL only) |
| `bash` | `*.sh`, `*.bash`, `*.bats` | [`plugins/codemap-bash/`](plugins/codemap-bash) | independent plugin |
| `_example_lang` | `*.example` | main repo | reference / smoke |

| Bridge | Purpose |
|---|---|
| `http_route` | Mints `scip-route` intermediates from `Symbol.extra["http_route"]` and `["http_calls"]` metadata; links client callers to server handlers regardless of language |
| `python_cross_module` | Resolves synthetic `scip-python . . . <module>/<leaf>.` targets emitted by the Python indexer to concrete local symbols when the file is in the index |

New language? You **never** need to PR the main repository — see
[Writing a plugin](#writing-a-plugin).

---

## Architecture

```
cli  →  core  ←  indexers
        ↑          ↑
        └── io ────┘
        ↑
        mcp
```

- **core** — pure business logic, Pydantic data models, SymbolID (SCIP
  format), call-graph algorithms (`walk_chain`, `shortest_path`)
- **io** — persistence adapters (JSON today, SQLite reserved for scale)
- **indexers** — pluggable language/asset indexers, discovered via
  `codemap.indexers` entry-point group
- **bridges** — pluggable cross-language resolvers, discovered via
  `codemap.bridges` entry-point group
- **cli** — Typer command surface
- **mcp** — MCP server, later sprint

Strict import-linter contracts (`pyproject.toml`) enforce the
dependency direction `cli → core ← indexers`, `cli → core ← io` on
every PR.

---

## Writing a plugin

CodeMap's indexers and bridges are plugin-first. Adding a new language is
a separate PyPI package — main repo is never touched. The
`codemap-typescript` package under `plugins/` is the reference
implementation:

```toml
# your-plugin/pyproject.toml
[project.entry-points."codemap.indexers"]
yourlang = "codemap_yourlang:YourLangIndexer"
```

That one line is the only coupling. After `pip install your-plugin`
your indexer appears in `codemap doctor` on identical terms.

Step-by-step guide: [`docs/plugin-guide.md`](docs/plugin-guide.md).
Reference: [`plugins/codemap-typescript/`](plugins/codemap-typescript).

---

## Performance

Baseline numbers (median, M-series single core, indexing the CodeMap
repo itself, 437 symbols / 1232 edges):

| Bench | Median | Target (design §21) |
|---|---:|---:|
| full index | 73 ms | ≤ 3 s |
| `callers` | 4.7 µs | ≤ 50 ms |
| `callees` | 26 µs | ≤ 50 ms |
| `walk_chain` depth 10 | 72 µs | ≤ 200 ms |

Re-run locally with `pytest -m bench -o addopts=""`. PRs that regress
any median by ≥ 20 % are blocked by CI (ADR-010). Full table and
methodology: [`docs/performance.md`](docs/performance.md).

---

## Documentation

| File | Topic |
|---|---|
| [`docs/cli.md`](docs/cli.md) | Every command, flag, JSON envelope, exit code |
| [`docs/configuration.md`](docs/configuration.md) | All config keys + merge order |
| [`docs/plugin-guide.md`](docs/plugin-guide.md) | How to write an indexer / bridge plugin |
| [`docs/performance.md`](docs/performance.md) | Baseline numbers + ADR-010 regression policy |
| [`docs/indexers/python.md`](docs/indexers/python.md) | Python indexer details |
| [`docs/bridges/http_route.md`](docs/bridges/http_route.md) | HTTP route bridge contract |
| [`docs/adr/`](docs/adr/) | Architecture decision records (1–12 + L001) |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes |

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The key invariant: **no
language is a first-class citizen**. Proposals that special-case any
ecosystem will be asked to refactor into the generic plugin protocol
(ADR-L001).

CI gates every PR through `ruff`, `mypy --strict`, `import-linter`,
`pytest --cov 80%`, and the benchmark suite.

---

## License

MIT — see [`LICENSE`](LICENSE).
