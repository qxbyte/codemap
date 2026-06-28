# CodeMap

**English** · [简体中文](./README.zh-CN.md)

> Language-neutral code index for AI agents — precise navigation without
> full-project search.

CodeMap builds a deterministic, AST-based index of your codebase so AI
agents (Claude Code, Cursor, Codex, etc.) can find call chains, route
mappings, and cross-file relationships without grepping the entire
project. Indexing is static, fast, and reproducible — no LLM in the
index path.

**Status**: 0.3.1 stable. Installable from PyPI as `codemap-core`
plus 17 `codemap-<lang>` plugins + 2 framework / output plugins
(`codemap-mybatis`, `codemap-aimemory`, added in 0.3.0; 0.3.1
adds the `codemap llm config` CLI).

> 👉 **In a hurry?** The [`INSTALL.md`](./INSTALL.md) guide is the
> definitive walkthrough — it covers `pipx` / `uv tool` / `pip`,
> language-plugin injection, offline distribution, troubleshooting, and
> a verbatim clean-machine validation log.

---

## Table of contents

- [Core principles](#core-principles)
- [Installation](#installation)
  - [1. Main CLI](#1-main-cli)
  - [2. Optional extras](#2-optional-extras)
  - [3. Language plugins](#3-language-plugins)
  - [4. Local clone (development)](#4-local-clone-development)
  - [4b. Install from git](#4b-install-from-git-track-main-pin-to-a-commit)
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
# Recommended: pipx provides environment isolation + a system-wide
# `codemap` command
pipx install codemap-core

# Plain pip (preferably into a venv)
pip install codemap-core

# Or with uv
uv tool install codemap-core
```

### 2. Optional extras

```bash
# `--watch` mode needs watchdog
pip install "codemap-core[watch]"
pipx install "codemap-core[watch]"

# Development tools (tests, lint, mypy, import-linter, benchmarks)
pip install "codemap-core[dev]"
```

### 3. Language plugins

Each non-Python language indexer ships as an **independent PyPI
distribution**. To add a language to a `pipx`-installed `codemap`, use
`pipx inject` so the plugin lands in the same isolated venv as the
main CLI:

```bash
# All 17 languages in one shot
pipx inject codemap codemap-typescript codemap-javascript codemap-vue \
                    codemap-java codemap-jsp codemap-go \
                    codemap-rust codemap-swift codemap-kotlin \
                    codemap-ruby codemap-php codemap-sql \
                    codemap-bash codemap-c codemap-cpp \
                    codemap-csharp codemap-scala
```

Plain pip (when `codemap-core` is installed via `pip`, not `pipx`):

```bash
pip install codemap-typescript codemap-javascript codemap-vue \
            codemap-java codemap-jsp codemap-go codemap-rust \
            codemap-swift codemap-kotlin codemap-ruby codemap-php \
            codemap-sql codemap-bash codemap-c codemap-cpp \
            codemap-csharp codemap-scala
```

Or one at a time when you only need a single language:

```bash
pipx inject codemap codemap-typescript   # or pip install codemap-typescript
```

Each plugin declares `codemap-core` as a dependency, so pip will pull
the engine if you don't already have it. After installation, `codemap
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
pip install -e plugins/codemap-c
pip install -e plugins/codemap-cpp
pip install -e plugins/codemap-csharp
pip install -e plugins/codemap-scala
```

### 4b. Install from git (track `main`, pin to a commit)

For users who want unreleased changes from `main` or to pin to a
specific commit, the git URL form still works:

```bash
# Track main
pip install git+https://github.com/qxbyte/codemap.git
pipx install git+https://github.com/qxbyte/codemap.git

# Pin to a commit
pip install git+https://github.com/qxbyte/codemap.git@2c3ed45

# A specific language plugin from a subdirectory
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-typescript"
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
┃ c             │ 0.1.0   │ c          │ *.c, *.h      │
┃ cpp           │ 0.1.0   │ cpp        │ *.cpp, *.cc, *.cxx, *.hpp, *.hh, *.hxx │
┃ csharp        │ 0.1.0   │ csharp     │ *.cs, *.csx   │
┃ scala         │ 0.1.0   │ scala      │ *.scala, *.sc │

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

# Knowledge recall — 0.3.5+ (codemap-aimemory plugin)
# Scans .ai-memory/knowledge/*.yml (written by specode-distill / task-swarm)
# and ranks by token overlap; returns top-K relevant knowledge.
# Designed to be called by specode at the start of the requirements phase.
codemap recall '<query>'                                 # default top-k 5, yaml output
codemap recall '<query>' -p /abs/project -k 10 -o json   # explicit project + json
codemap recall '<query>' -t rules,pitfalls               # filter categories
codemap recall --from-spec requirements.md               # 0.3.6+: use spec file as query
codemap recall '<query>' --with-content                  # 0.4.0+: include rule/pit/case core fields
# Every result carries `freshness_score`/`ranked_score`/`stale` since 0.4.0;
# fresher hits outrank stale ones at the same token score (180-day half-life + code-churn decay).
# With `codemap-semantic-index` plugin installed (P1-3, since v0.4.2), recall
# automatically does hybrid token+embedding ranking with RRF fusion.

# Semantic recall (requires opt-in `codemap-semantic-index` plugin, P1-3)
codemap embed install               # interactive picker; downloads default Qwen3-Embedding-0.6B (1.2GB)
codemap embed                       # incremental embed of knowledge-base/*.md
codemap embed --rebuild             # force full rebuild
codemap embed backend set --provider qwen --api-key sk-xxx  # switch to cloud Qwen embedding

# Machine-readable output: all commands take --json
codemap --json callers '<symbol-id>'

# Optional LLM enrichment (codemap-aimemory plugin, 0.3.0+)
codemap llm config set api-key sk-xxx       # persist to ~/.config/codemap/llm.yaml
codemap llm config set base-url https://api.deepseek.com/v1
codemap llm config set model deepseek-chat
codemap llm config show                     # masked-key view + value source
codemap enrich .                            # fills .ai-memory/enrichment/*.yml
codemap enrich . --dry-run                  # count fn/method symbols, no API call
```

Exit codes follow `sysexits.h` (ADR-005); see
[`docs/cli.md`](docs/cli.md#exit-codes) for the table.

---

## Output formats

`codemap index` produces two parallel directories at the project root:

```
<project>/
├── .codemap/        ← deterministic, machine-friendly index (queried by `codemap …`)
└── .ai-memory/      ← four-layer-memory-model L1 layout (consumed by AI agents)
```

### `.codemap/` — deterministic index (JSON, 7 files)

| File | Contents |
|---|---|
| `symbols.json` | All symbols keyed by `SymbolID`. Each entry: `kind`, `language`, `file`, `range`, `signature`, `annotations`, `confidence`, `extra` (per-language metadata: `pending_calls`, `http_route`, `supertypes`, `imports`, `params`, `return_type`, `change_count_90d`, …). |
| `edges.json` | Directed relations: `calls` / `extends` / `implements` / `overrides` / `references` / `routes_to` / `maps_to` / `imports` / `accesses_table`. Each carries `confidence` ∈ {`high`, `medium`, `low`}. |
| `routes.json` | HTTP routes minted by the `http_route` bridge from `extra["http_route"]`. |
| `aliases.json` | Synthetic intermediate ↔ real symbol links (e.g. route → handler). |
| `manifest.json` | Project root, `codemap_version`, registered indexers + bridges + their versions, per-file sha256 / mtime / language. |
| `diagnostics.json` | Indexer / bridge warnings collected during the run (severity + code + message + producer). |
| `.lock` | Cross-process write lock; do not edit. |

### `.ai-memory/` — four-layer memory model

Written by `codemap-aimemory` (L0+L1, every `codemap index`) and
optionally by [sibling tools](#integration-with-specode-distill-and-task-swarm)
(`specode-distill` for L2/L3, `task-swarm` for the auto-ingested
`cases` + `pitfalls`). AI agents read this tree directly. Stable
`entity_id` slugs are derived from the SCIP `SymbolID`
(e.g. `fn-calcPrice` / `cls-OrderService` / `tbl-sf_coupon`).

```
.ai-memory/
├── project.yml              ← L0   (codemap-aimemory 0.3.2+)
│                              tech stack / dependencies / git remote /
│                              top dirs / configs — best-effort autodetect
│
├── entities/                ← L1   (codemap-aimemory 0.3.0+)
│   ├── functions.yml          fn-/cls- entities with calls / called_by /
│   │                          related_tables / signature / line_range /
│   │                          confidence / change_count_90d /
│   │                          business_meaning
│   ├── tables.yml             tbl-* table entities
│   ├── files.yml              file-* file entries
│   └── modules.yml            mod-* per-file aggregates (0.3.3+):
│                              {id, path, language, fn_count, cls_count,
│                               functions[], classes[]}
│
├── relations/               ← L1
│   ├── call-graph.yml         `{from, to, type=calls, confidence}`
│   ├── table-relations.yml    `{from, to, type=accesses_table, confidence}`
│   └── rule-constraints.yml   empty placeholder (L2 owns the channel)
│
├── enrichment/              ← L1 OPTIONAL — LLM-generated overlays
│   └── <sha1[:12]>.yml        `{symbol_id, business_meaning,
│                                related_rules, confidence:"llm",
│                                source_model, generated_at}`
│
├── _global/                 ← L1↔L2/L3 lookup (codemap-aimemory 0.3.4+)
│   └── entities.yml           Cross-walk: every entity_id (code or
│                              knowledge) with `source` ∈
│                              {code, knowledge, both} +
│                              `knowledge_refs` (which knowledge yml
│                              mention this entity). Backs `codemap recall`.
│
├── _semantic/               ← P1-3, OPTIONAL — written by codemap-semantic-index
│   ├── chunks.json            chunked text + metadata (model-independent)
│   ├── vectors.npy            (n_chunks, 1024) float32 (model-specific)
│   ├── model_id.txt           active backend fingerprint
│   └── manifest.json          text_hash → chunk_id (drives incremental embed)
│
└── knowledge/               ← L2 + L3 (NOT written by codemap itself —
                              produced by specode-distill / task-swarm;
                              codemap-aimemory reads it to build
                              _global/entities.yml and to power recall)
    ├── rules/    rule-*.yml         L2 business rules / mechanisms
    ├── business/ biz-*.yml          L2 business processes / UI features
    ├── modules/  mod-*.yml          L2 module maps (table / call_chain)
    ├── cases/    case-*.yml         L3 historical implementation cases
    └── pitfalls/ pit-*.yml          L3 reusable failure / fix lessons
```

Two-hop fan-out: when a Java method `maps_to` a `sql_mapping` that
`accesses_table` T, T automatically lands on the method's
`related_tables`. So `fn-selectByUser.related_tables = [tbl-sf_coupon]`
without the agent needing to follow the chain itself.

---

### Integration with `specode-distill` and `task-swarm`

codemap-aimemory owns L0+L1; **L2+L3 (`knowledge/`) come from sibling
tools in the [pluginhub](https://github.com/qxbyte/pluginhub) family**.
The integration is one-way and loose — codemap doesn't import the
others, just reads their yml output when present:

| Layer | Writer | When |
|---|---|---|
| L0 `project.yml` | `codemap-aimemory` (this) | every `codemap index` |
| L1 `entities/*`, `relations/*`, `enrichment/*` | `codemap-aimemory` (this) | every `codemap index` (enrichment is opt-in via `codemap enrich`) |
| L1↔L2/L3 `_global/entities.yml` | `codemap-aimemory` (this) | every `codemap index`, mining `knowledge/*.yml` if present |
| L1.5 `_semantic/*` (chunks + vectors) | `codemap-semantic-index` (opt-in plugin, P1-3) | explicit `codemap embed` |
| L2/L3 `knowledge/rules,business,modules,cases,pitfalls/*.yml` | `specode-distill` (`pluginhub` plugin, specode 3.0+; 3.3.1 surfaces `CLAUDE.md / AGENT.md` paths into `requirements.md` via AI-EDS v0.9 痛点 #14 方案 D; 3.3.2 adds cache vs marketplace drift hint; 3.4.0 adds autonomous-mode defaults for CI / unattended use) | user runs `/specode:specode-distill <slug>` or accepts the prompt at end of specode's acceptance phase |
| L3 `knowledge/cases/case-*.yml` + `knowledge/pitfalls/pit-*.yml` | `task-swarm` (`pluginhub` plugin, 0.7+ delegates yml/md writes to `codemap knowledge write`; 0.7.3 + 0.7.4 surface `CLAUDE.md / AGENT.md` paths into every subagent `task.md` + drop `_PROJECT_AGENT_DOCS.md` sentinel into inbox; 0.8.0 adds `init` dedupe with `--on-existing` flag) | every successful `task_swarm.py resolve` |

When `codemap-semantic-index` is installed, `codemap recall` automatically becomes **hybrid (token + embedding) ranking via Reciprocal Rank Fusion** (k=60), then multiplied by `freshness_score`. Embedding hits that token recall missed surface naturally. Without the plugin installed, recall remains token-only — no behaviour change for users who don't want embeddings.

Each `specode-distill` / `task-swarm` write **also** produces a twin
markdown file under `<project_root>/knowledge-base/<category>/<id>.md`
(same stem as the yml). The twin md preserves narrative / ascii flow
charts / wikilink-style tables that field-level yml necessarily
flattens, and is intended as the high-quality slicing source for a
future embedding indexer. codemap itself doesn't read `knowledge-base/`
today — `codemap recall` operates on the yml side; the md exists to
serve human reading and future P1-3 semantic search.

**Use `codemap recall '<query>'` to query the union** (code-side entity
hits + token overlap against every `knowledge/*.yml`). This is what
specode 2.1+ calls from its requirements phase to inject "已知约束 /
历史坑" context before drafting a new spec. See `docs/integration.md`
(coming) for the full agent-side workflow.

No part of `knowledge/` is required for codemap to function. On a
project that has never run `specode-distill` or `task-swarm`,
`_global/entities.yml` simply lists code entities with
`source: code`, and `codemap recall` returns matched code entities
with empty `knowledge: []`.

---

## LLM configuration (optional)

The core index is **always LLM-free** — `codemap index` never calls any
LLM. Only the optional `codemap enrich` command in `codemap-aimemory`
writes the `enrichment/` overlay, and only when **you** invoke it. The
existence of an API key is the on/off switch: without one, `codemap
enrich` exits with a clear error and no network call is made.

Three configuration sources, **first non-empty wins**:

1. **CLI flag** — `--api-key`, `--base-url`, `--model`, `--backend`
2. **Environment variable** — `CODEMAP_LLM_API_KEY` (also
   `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); `CODEMAP_LLM_BASE_URL`
   (also `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`);
   `CODEMAP_LLM_MODEL`; `CODEMAP_LLM_BACKEND`
3. **Persistent file config** — `~/.config/codemap/llm.yaml` (managed
   by `codemap llm config set/unset/show`; written `chmod 600`)
4. Built-in defaults — backend `openai`, model `gpt-4o-mini`

### Common provider endpoints (OpenAI-compatible — `--backend openai`)

| Provider | Model example | Base URL |
|---|---|---|
| OpenAI | `gpt-4o-mini` | `https://api.openai.com/v1` *(default)* |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| 智谱 GLM | `glm-4-flash` | `https://open.bigmodel.cn/api/paas/v4/` |
| MiniMax | `abab6.5s-chat` | `https://api.minimax.chat/v1` |
| 月之暗面 Kimi | `moonshot-v1-8k` | `https://api.moonshot.cn/v1` |
| 阿里通义 | `qwen-plus` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 小米 MiMo | `mimo-large` | *(per vendor docs; OpenAI-compatible)* |
| Ollama (local) | `llama3` | `http://localhost:11434/v1` — use `--backend ollama` (key not needed) |
| Anthropic native | `claude-sonnet-4-5` | *(use `--backend anthropic`; requires `anthropic` SDK via `pip install codemap-aimemory[llm]`)* |

Example with DeepSeek:

```bash
codemap llm config set base-url https://api.deepseek.com/v1
codemap llm config set api-key sk-xxx
codemap llm config set model deepseek-chat
codemap enrich .
```

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
| `c` | `*.c`, `*.h` | [`plugins/codemap-c/`](plugins/codemap-c) | independent plugin |
| `cpp` | `*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx` | [`plugins/codemap-cpp/`](plugins/codemap-cpp) | independent plugin |
| `csharp` | `*.cs`, `*.csx` | [`plugins/codemap-csharp/`](plugins/codemap-csharp) | independent plugin |
| `scala` | `*.scala`, `*.sc` | [`plugins/codemap-scala/`](plugins/codemap-scala) | independent plugin |
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
