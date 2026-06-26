# Changelog

All notable changes to CodeMap will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
During `0.x`, MINOR may introduce breaking changes — they will be marked `BREAKING:`.

## [Unreleased]

## [0.3.6] — 2026-06-26

Lockstep version-only bump across all **20 packages**; the only source
change is in `codemap-aimemory` — adds an alternate input shape to
`codemap recall` that takes a spec file path instead of a free-text
query, so downstream automation (specode-distill / specode-continue)
can call it without having to hand-pick keywords.

### `codemap-aimemory` — `codemap recall --from-spec <path>`

* New `--from-spec` / `-f` option on `codemap recall`. Reads the given
  markdown file (typically `<specsRoot>/<slug>/requirements.md`) and
  uses its full text as the recall query. Mutually exclusive with
  the positional query argument.
* The positional `query` is now optional; exactly one of `query` or
  `--from-spec` must be supplied (otherwise exit 2 with a clear
  error message).
* When `--from-spec` is used the result yaml/json carries:
  - `from_spec: <abs path>` — the source file
  - `query: "<from-spec:<filename>>"` — short stand-in instead of
    the entire spec body (keeps the result compact and avoids
    accidentally leaking the full requirements into logs)
* Tokenizer / ranking logic unchanged; pure additive on the input
  surface. Existing positional-query call sites are unaffected.
* 8 new CLI tests in `test_recall_cli.py` cover both shapes,
  mutual-exclusion errors, missing-file error, `.ai-memory`
  presence check, and the types filter on the spec path.
  Aimemory plugin tests: 115 → 123.

### Roadmap pairing

The companion change in `pluginhub` extends `specode-distill`'s
breakdown step (step 4) with a pre-step that calls `codemap recall
--from-spec --types rules,pitfalls` to surface existing pitfalls /
rules before proposing new knowledge — closing the AI-EDS roadmap
**P2-2** loop (write rules with awareness of historical pitfalls).

## [0.3.5] — 2026-06-26

Lockstep version-only bump across all **20 packages**; the only source
change is in `codemap-aimemory` — first half of the AI-Enterprise-
Delivery-System roadmap **P3-1**: a CLI that downstream tools (specode)
can call to recall relevant knowledge before drafting requirements.

### `codemap-aimemory` — `codemap recall <query>` CLI (P3-1, half 1)

* New module `codemap_aimemory.recall` with a pure scorer
  `recall(query, project_root, top_k, types)` that scans
  `<project_root>/.ai-memory/knowledge/{rules,business,modules,cases,
  pitfalls}/*.yml` and ranks by token overlap with each yml's
  searchable fields (title / tags / statement / related_code / fix /
  symptom / …). Title hits weighted higher than body hits.
* New `codemap_aimemory.recall_cli` registers the **`codemap recall`**
  subcommand via the `codemap.cli_commands` entry-point (the same
  group that hosts `enrich` and `llm`). Flags:
  `--project/-p <abs>` (default cwd), `--top-k/-k N` (default 5),
  `--types/-t rules,business,…` (category filter),
  `--output/-o yaml|json` (default yaml).
* Output carries `query`, parsed `tokens`, `matched_entities` (id-based
  hits against `_global/entities.yml`), and `knowledge` rows
  (`knowledge_id`, `type`, `category`, `title`, `summary`, `score`,
  `file`).
* Tokenizer is dependency-free: English/digit words ≥ 2 chars +
  Chinese char-bigrams. Good enough for the few-word requirements
  query; embeddings land in P1-3.
* 18 new unit tests (`test_recall.py`) cover tokenizer edge cases
  (English / Chinese / mixed / empty), ranking, top-k, type filter,
  title-weight, related_code/symptom/fix matching, malformed yml,
  matched_entities, and full output shape.

### Roadmap pairing

The companion change in `pluginhub` extends `specode`'s requirements
phase to invoke `codemap recall` before writing `requirements.md` and
inject the top hits into the "已知约束 / 历史坑" section — closing the
P3-1 loop end-to-end.

## [0.3.4] — 2026-06-25

Lockstep version-only bump across all **20 packages**; the only source
change is in `codemap-aimemory` — closes the AI-Enterprise-Delivery-
System roadmap **P1-2** (global entity index — business ↔ code).

### `codemap-aimemory` — global entity cross-walk (P1-2)

* New module `codemap_aimemory.global_entities` with a pure aggregator
  `build_global_entities(out_dir, code_entity_ids)` that walks the
  emitter's own entity vocabulary (`fn-*`, `cls-*`, `tbl-*`, `mod-*`)
  alongside any `<out_dir>/knowledge/{rules,business,modules,cases,
  pitfalls}/*.yml` produced by `spec-distill v2`. Knowledge yml is
  scanned for three reference channels: `related_code[].entity`,
  `related_knowledge[]`, and `affects[]` (pitfalls). Malformed yml
  is silently skipped — a hand-edited knowledge file never crashes
  the build.
* `AiMemoryEmitter` now writes **`.ai-memory/_global/entities.yml`**:
  one row per entity with `id`, inferred `type` (from id prefix),
  `source` (`code` / `knowledge` / `both`), and `knowledge_refs`
  (every knowledge_id that mentions this entity). Top-level `counts`
  partition: `total` / `code_only` / `knowledge_only` / `both`.
* Type inference covers all current prefixes: `fn-` → function,
  `cls-` → class, `tbl-` → table, `mod-` → module, `rule-` → rule,
  `biz-` → business_process, `case-` → case, `pit-` → pitfall.
* Closes the L1 ↔ L2/L3 lookup gap: an Agent answering "where is
  `sf_coupon` referenced?" now hits one yml instead of walking the
  whole knowledge tree.
* 13 new unit tests (`test_global_entities.py`) + 1 emitter integration
  test cover empty / partial / cross-linked / malformed scenarios.

## [0.3.3] — 2026-06-25

Lockstep version-only bump across all **20 packages**; the only source
change is in `codemap-aimemory` — completing the P1-1 follow-up flagged
in the AI-Enterprise-Delivery-System roadmap (modules view of L1).

### `codemap-aimemory` — per-file module aggregator

* New module `codemap_aimemory.modules` with a pure aggregator
  `aggregate_modules(symbols, entity_ids)` grouping `fn-*` / `cls-*`
  entities by their owning file. Each module dict carries
  `id` (`mod-<slug>`), `type: module`, `path`, `language`,
  `fn_count`, `cls_count`, `functions` (sorted entity IDs), `classes`
  (sorted entity IDs).
* Slug strategy strips common source roots (`src/`, `src/main/java/`,
  `lib/`, `app/`) and the file extension, then turns slashes into
  dashes: `src/codemap/cli/commands/index.py` →
  `mod-codemap-cli-commands-index`, `src/main/java/com/demo/Svc.java`
  → `mod-com-demo-Svc`.
* `AiMemoryEmitter` now writes **`.ai-memory/entities/modules.yml`**
  alongside the existing `functions.yml` / `tables.yml` / `files.yml`
  / `project.yml`. Files containing only non-fn/cls symbols (e.g.
  MyBatis XML tables) are intentionally omitted — they're already
  covered by `tables.yml`.
* 10 new unit tests (`test_modules.py`) + 1 emitter integration test
  cover slug edge cases, sorting, fn/cls counts, language capture,
  and exclusion of table-only files.

## [0.3.2] — 2026-06-25

Lockstep version-only bump across all **20 packages** to keep the family
in sync; the only source change is in `codemap-aimemory`.

### `codemap-aimemory` — L0 project meta emitter (P0-3)

* New module `codemap_aimemory.project_meta` with a pure collector
  `build_project_meta(project_root)` that returns a YAML-safe dict:
  `schema_version`, `generated_at`, `root`, `tech_stack`
  (`primary_language` + `manifests`), `languages` (file-extension
  counts), `dependencies` (`runtime` + `dev`), `git`
  (`remote` / `branch` / `head`), `top_dirs`, `configs`.
* `AiMemoryEmitter` now writes **`.ai-memory/project.yml`** alongside the
  existing `entities/` and `relations/` outputs — this is the L0 sheet
  of the four-layer memory model (per the AI-Enterprise-Delivery-System
  knowledge-base design). Deterministic, no LLM, runs every
  `codemap index`.
* Manifest detection covers `pyproject.toml` / `setup.py` /
  `requirements.txt` / `package.json` / `pom.xml` / `build.gradle{,.kts}`
  / `Cargo.toml` / `go.mod` / `Gemfile`. Node primary-language picks
  `vue` / `typescript` / `javascript` from observed file extensions.
* Language scan walks the tree but skips `.git` / `.venv` /
  `node_modules` / `dist` / `build` / `target` / `__pycache__` and the
  usual hidden caches so dependency vendoring doesn't pollute counts.
* Git block is best-effort via `git config`/`rev-parse`; if
  `project_root/.git` is absent the block is empty (`{}`) — no crash.

## [0.3.1] — 2026-06-25

Quick follow-up to 0.3.0. Lockstep version-only bump across all **20
packages** to keep the family in sync; the only source change is in
`codemap-aimemory`.

### `codemap-aimemory` — LLM CLI configuration

* New subcommand group **`codemap llm config`** (registered through the
  `codemap.cli_commands` entry-point group introduced in 0.3.0):
  * `codemap llm config set api-key <key>` — persist to
    `~/.config/codemap/llm.yaml` (or `$XDG_CONFIG_HOME/codemap/llm.yaml`),
    written `chmod 600` because it carries a credential.
  * `codemap llm config set base-url <url>` / `model` / `backend`.
  * `codemap llm config unset <key>` — clear one field; the on-disk
    file only contains non-`None` values.
  * `codemap llm config show` — print the effective config with one of
    `[env]` / `[file]` / `[default]` annotated per field; API keys are
    masked.
  * `codemap llm config path` — print the config file location.
* `codemap enrich` resolution order is now (first non-empty wins):
  CLI flag → env var → file config (new in 0.3.1) → built-in defaults.
* Behavioural reminder: **API key is the LLM on/off switch.**
  `codemap index` never calls any LLM; `codemap enrich` without a key
  errors out cleanly, never silently. No background LLM traffic.

### Documentation

* README + README.zh-CN: new "Output formats" section documenting every
  file under `.codemap/` and `.ai-memory/` (kind, shape, who consumes it).
* README + README.zh-CN: new "LLM configuration" section with the
  three-source resolution order and a Chinese / open-source LLM endpoint
  cheatsheet (DeepSeek, GLM, MiniMax, Kimi, Qwen, MiMo, Ollama, native
  Anthropic) — all use `--backend openai` with their own `base-url`.
* INSTALL: bump heading and mention the new CLI.

### Plugin tests

19 new unit tests in `codemap-aimemory` covering: XDG path resolution,
load / save / unset round-trip, `chmod 600` on save, corrupt-YAML
graceful fallback, dash-vs-underscore key aliasing, CLI set / show /
unset / path, source-annotation correctness in `show`. Plugin test
total: 38 → 57. Other plugins unchanged.

## [0.3.0] — 2026-06-25

The four-layer-memory-model L1 release. The plugin family grows from
**18 to 20** distributions; every package bumps in lockstep to `0.3.0`,
and every plugin's `codemap-core` dependency widens to `>=0.3.0,<0.4`.

### New plugins (opt-in)

* **`codemap-mybatis`** — MyBatis Mapper XML indexer. Per-file XML
  parsing yields `sql_mapping` symbols + `table` symbols + DML
  `accesses_table` edges (confidence graded by SQL complexity —
  static / dynamic-tag / `${}` substitution). A new `MyBatisLinkBridge`
  emits `maps_to` edges from Java Mapper interface methods to their
  backing XML statements (requires `codemap-java` installed).
* **`codemap-aimemory`** — emits the four-layer memory model's L1
  layout (`.ai-memory/entities/*.yml` + `.ai-memory/relations/*.yml`)
  so AI agents can consume the index directly with stable
  `entity_id` slugs (fn-* / cls-* / tbl-*). Atomic per-file writes
  (tmp + rename). Includes an optional LLM enrichment overlay — the
  core index itself remains LLM-free; enrichment writes to a
  separate `enrichment/` directory keyed by `symbol_id` and is
  merged only at emit time.

### New core capability

* **Project-level indexer protocol** (`codemap.indexers.project_base`).
  Mirrors the per-file `Indexer` but consumes the entire project in
  one pass, for engines whose output is whole-project (Java semantic
  resolver, future SCIP-backed importers). Lazy-discovered through
  the new `codemap.project_indexers` entry-point group.
* **Emitter protocol** (`codemap.emitters`) — third plugin layer
  alongside indexers / bridges. Registered through
  `codemap.emitters` entry-point group with the same Protocol +
  Registry pattern. The orchestrator runs emitters as the last
  phase of `codemap index` (after bridges + hotspots).
* **CLI subcommand registration via entry-points**
  (`codemap.cli_commands`). Plugins can ship typer subcommands —
  `codemap-aimemory` uses this to register `codemap enrich`.
* **Git change-hotspot analyzer** (`codemap.core.git_hotspots`).
  Language-neutral; surfaces `change_count_90d` on every symbol's
  `extra`. Graceful skip on non-git / unavailable git.
* `EdgeKind` adds `overrides`, `accesses_table`; `SymbolKind` adds
  `table`.

### Java engine rewrite (ADR-0013)

* **`codemap-java`** moves from declaration-only to a full call
  graph. The per-file indexer now captures `imports`, `supertypes`,
  `pending_calls` (raw invocation records), method `params` /
  `return_type`, and field `type` on `Symbol.extra`. A new
  `JavaCallResolverBridge` (registered as `java_calls`) does
  project-wide FQN resolution to emit `calls` / `extends` /
  `implements` edges at `confidence=medium`. ADR-0013 documents
  the deliberate trade-off (precision ceiling drops from
  full-semantic `high` to FQN-resolved `medium`, in exchange for
  zero external toolchain — no scip-java, no JVM build needed).
* Spring annotation extraction: type / method `@Annotation` nodes
  land on `Symbol.annotations`; the indexer combines class-level
  `@RequestMapping` prefix with method verb mappings
  (`@GetMapping` / `@PostMapping` / …) and writes `http_route`
  metadata so the existing `http_route` bridge auto-mints route
  intermediates.

### `codemap-vue` extends

* Captures `axios.<verb>(...)` / `this.$axios.<verb>(...)` /
  `fetch(...)` invocations inside script blocks, attaching
  `{method, url, confidence}` records to the enclosing
  function/method symbol's `extra["http_calls"]`. The existing
  `http_route` bridge now connects Vue clients to Spring routes
  automatically.

### `codemap enrich` CLI (new)

```bash
codemap enrich --backend openai     --model gpt-4o-mini
codemap enrich --backend anthropic  --model claude-sonnet-4-5
codemap enrich --backend ollama     --model llama3
codemap enrich --base-url http://my-proxy/v1 --api-key sk-…
```

Reads `.codemap/`, calls the configured LLM for each
function/method symbol, writes overlay YAML files under
`.ai-memory/enrichment/`. Env-var fallback chain:
`CODEMAP_LLM_API_KEY` → `ANTHROPIC_API_KEY` → `OPENAI_API_KEY`;
`CODEMAP_LLM_BASE_URL` → `OPENAI_BASE_URL` → `ANTHROPIC_BASE_URL`.
The next `codemap index` merges the overlay into
`entities/functions.yml`. `--dry-run` reports without calling.

### Default prune dirs

`DEFAULT_PRUNE_DIRS` now includes `target` (Maven) and `out`
(Gradle IDE default) so Java/Kotlin/Scala projects don't double-
index build output trees.

### New import-linter contract

`emitters may not import cli/mcp/io` keeps the new emitter layer
honest to the same dependency rules as indexers and bridges.

## [0.2.2] — 2026-06-05

Lockstep version-only bump across all **18 packages** to keep the
plugin family in sync. No source changes.

Reason: between `v0.2.0` and now, `codemap-core` shipped a `0.2.1`
patch (PR #9 — read version from package metadata instead of
hardcoding) without a coordinated plugin bump, leaving the 17 plugin
distributions at `0.2.0` and `codemap-core` at `0.2.1`. This release
re-aligns the family at `0.2.2` so `pipx install codemap-core==0.2.2`
plus `pipx inject codemap codemap-<lang>==0.2.2` is a clean,
single-version install for every supported language.

## [0.2.0] — 2026-06-04

Plugin family grows **15 → 18**. All packages bump in lockstep to
`0.2.0` — the 15 existing distributions get a version-only bump, the
three new distributions ship at `0.2.0` for the first time. Every
plugin's `codemap-core` dependency is widened to `>=0.2.0,<0.3` so
all 17 plugins resolve against the new engine.

### Added — Three new language plugins (`codemap-javascript`, `codemap-vue`, `codemap-jsp`)

Each ships as an independent PyPI distribution.

* **`codemap-javascript`** — covers `*.js` / `*.jsx` / `*.mjs` /
  `*.cjs` via `tree-sitter-javascript`. Symbol coverage mirrors
  `codemap-typescript` (top-level functions, classes with methods,
  module-level `const` / `let` / `var`). Sibling of
  `codemap-typescript` — install either or both depending on the code
  base.

* **`codemap-vue`** — covers `*.vue` Single File Components. Since
  `tree-sitter-vue` is not on PyPI, the plugin uses a permissive
  regex-driven SFC scanner (`codemap_vue.sfc.extract_script_blocks`)
  to locate every top-level `<script>` block and read its `lang=`
  attribute, then dispatches the inner bytes to
  `tree-sitter-javascript` (always required) or
  `tree-sitter-typescript` (optional `[typescript]` extra, only
  required when a block declares `lang="ts"` / `lang="tsx"`).
  Symbol line numbers are translated back to the original `.vue`
  coordinate space so `codemap get` jumps to the right line even
  when `<script>` follows a long `<template>`.

* **`codemap-jsp`** — covers `*.jsp` / `*.jspx` / `*.tag` / `*.tagx`
  for legacy Java web projects. Scans top-level constructs via regex
  (`codemap_jsp.sfc.extract`) — page imports, includes, declaration
  blocks (`<%! ... %>`), scriptlets, `<form action="...">`, and
  `<a href="...">` — then parses each declaration block as a Java
  member context using a synthetic `class _S { … }` wrapper so
  `tree-sitter-java` emits `field_declaration` / `method_declaration`
  / nested `class_declaration` rather than `local_variable_declaration`.
  Form actions and links are surfaced as `extra.http_client_calls` on
  the page-level pseudo-class symbol, ready to be linked to server
  controllers by the `http_route` bridge — the standard JSP →
  Controller navigation chain.

`codemap doctor` now lists **18 indexers** (4 built-in + 14 plugins).

## [0.1.0] — 2026-06-03

First stable PyPI release. The CLI is now installable via:

```bash
pipx install codemap-core
# or
pip install codemap-core
```

…plus language adapters as separate distributions (`codemap-bash`,
`codemap-c`, `codemap-cpp`, `codemap-csharp`, `codemap-go`,
`codemap-java`, `codemap-kotlin`, `codemap-php`, `codemap-ruby`,
`codemap-rust`, `codemap-scala`, `codemap-sql`, `codemap-swift`,
`codemap-typescript`). `pipx inject codemap codemap-<lang>` is the
canonical pattern for adding language support to a `pipx`-installed
CLI.

### Changed — `README.md` / `INSTALL.md` switch to PyPI-first installation

Both `README.md` / `README.zh-CN.md` / `INSTALL.md` / `INSTALL.zh-CN.md`
and the 14 plugin READMEs now show `pip install codemap-core` and
`pip install codemap-<lang>` as the primary install path. The
`git+https://github.com/qxbyte/codemap.git[#subdirectory=…]` form is
retained as a fallback for users who want to track `main` or pin to a
specific commit before the next PyPI release.

### Fixed — `publish.yml`: `uv venv` does not bootstrap `pip` (2026-06-01)

The publish workflow's "Create isolated build venv" step was calling
`<venv>/bin/pip`, but `uv venv` (unlike `python -m venv`) intentionally
does not install `pip` into the venv. All 15 publish jobs failed at
exit 127 ("`pip: command not found`") under tag `v0.1.0a2`.

Fix: use `uv pip install --python <venv>/bin/python build twine`, the
same shape as the `bench.yml` fix in PR #3. Validated under tag
`v0.1.0a3` — 16/16 jobs green on TestPyPI.

### Added — `bench.yml`: PR-vs-main median delta comparison (2026-05-31)

The benchmark CI workflow now checks out `main` into a separate
`git worktree`, runs the `pytest-benchmark` suite against both PR HEAD
and main, then compares per-test median deltas. Threshold: ≥20%
regression on any benchmark fails the job; ≤−20% improvement and
in-band changes pass with `warn` / `ok` flags surfaced in the job
summary.

### Documented — PyPI rate-limit findings

Empirically, PyPI applies a per-account new-project-creation throttle:
roughly **4 new project registrations per 24-hour sliding window**.
File uploads (`.whl` / `.tar.gz`) to already-existing projects use a
separate, much looser bucket. The 0.1.0 release was paced across two
days to stay within this limit; subsequent maintenance releases are
unaffected because the projects already exist. The corresponding
support ticket is `pypi/support#10881`.

## [0.1.0a1] — 2026-05-30

First PyPI release rehearsal. Pre-release artifacts are published to
TestPyPI and (rate-permitting) PyPI under the new distribution names.

### Changed — Distribution rename: `codemap` → `codemap-core`

The PyPI distribution name for the main package becomes `codemap-core`.
Reason: `codemap` is held by an unrelated, actively-maintained PyPI
project (Sarthak Mishra, latest `2.0.0`); `code-map` (the obvious
hyphenated variant) is rejected by PyPI's similarity check because the
edit distance from `codemap` is 1. The `-core` suffix mirrors the
plugin naming convention — `codemap-core` is the engine, `codemap-java`
/ `codemap-go` / etc. are language adapters.

Behavior:

* **Import path is unchanged** — `from codemap.core.models import Symbol`
  still works; the wheel still ships `src/codemap/` to `site-packages/codemap/`.
* **CLI command is unchanged** — `codemap doctor`, `codemap index .`, etc.
  still appear on `$PATH` after install.
* **Install command does change** — users moving from a git-based install
  to PyPI will use `pip install codemap-core` (not `pip install codemap`).

### Changed — Plugins now depend on `codemap-core` with a version range

Each of the 14 language plugins replaces its bare `"codemap"` dependency
with `"codemap-core>=0.1.0a1,<0.2"`. The lower bound admits the alpha
series; the upper bound stops a future BREAKING bump to `0.2.x` from
silently pulling an incompatible engine.

### Added — `.github/workflows/publish.yml` (Trusted Publishing)

Tag-driven publish pipeline:

* `v<X>.<Y>.<Z>(a|b|rc)<N>` → TestPyPI
* `v<X>.<Y>.<Z>`            → PyPI
* anything else             → workflow fails fast

15-package matrix (1 main + 14 plugins), each step:

1. `uv` installs Python 3.13 + `build` + `twine`
2. `python -m build` produces `dist/*.tar.gz` and `dist/*.whl`
3. `twine check dist/*` validates metadata + README rendering
4. `pypa/gh-action-pypi-publish@release/v1` uploads via OIDC

Uses GitHub Environments (`pypi` / `testpypi`) for Trusted Publishing.
`id-token: write` permission grants the OIDC token; no PyPI API token
is stored in repository secrets. `skip-existing: true` makes re-runs
idempotent.

### Added — `twine>=5.0` to `[dev]` extras

For local manual `twine check` / `twine upload` outside CI.

### Added — Distribution metadata polish

Main `pyproject.toml` gains:

* `Environment :: Console`,
  `Intended Audience :: Information Technology`,
  `Operating System :: MacOS`,
  `Operating System :: POSIX :: Linux`,
  `Topic :: Software Development :: Libraries :: Python Modules`
  classifiers.
* `Changelog` URL in `[project.urls]`.

### Validated locally (2026-05-30)

* `python -m build` succeeds for all 15 packages; 30 artifacts produced
  (15 sdists + 15 wheels).
* `twine check dist/* plugins/*/dist/*` reports **30 PASSED**.
* All 15 names uploaded to **TestPyPI** successfully:
  <https://test.pypi.org/project/codemap-core/0.1.0a1/> and the 14
  matching `codemap-<lang>` siblings.
* Production **PyPI** upload was rate-limited (HTTP 429) after the
  first batch; a background retry loop with `--skip-existing` brings
  the remaining names up over the following minutes.

### Added — Bilingual `INSTALL.md` install guide (2026-05-30)

- New `INSTALL.md` (English) and `INSTALL.zh-CN.md` (Simplified
  Chinese) walk through `pipx` / `uv tool` / `pip` installation paths
  for the main CLI, then `pipx inject` / `uv tool inject` / `pip
  install` for the 14 language plugins. Covers the `[watch]` extra,
  offline wheel-bundle distribution, upgrade/uninstall, and a
  troubleshooting matrix for the common gotchas (Python < 3.11,
  `command not found`, plugin not discovered, slow first install,
  `tree-sitter-*` build failures, partial plugin removal).
- Both files end with a verbatim **validation log** captured on a
  fresh Python 3.12 virtualenv on 2026-05-30 against
  [`c4cd436`](https://github.com/qxbyte/codemap/commit/c4cd436):
  install (2 m 05 s), `doctor` on a clean install (2 indexers, 2
  bridges), Java plugin inject (15.6 s, auto-discovered), index a
  mixed Java + Python fixture (6 symbols, 1 route, 0 diagnostics),
  and `--json` output for AI agents.
- Both `README.md` and `README.zh-CN.md` now link to the install
  guide near the top, ahead of their own (lighter) install sections.

### Added — C / C++ / C# / Scala independent PyPI plugins (2026-05-30)

- `plugins/codemap-c/` — `tree-sitter-c` backed. Captures
  `function_definition`, named `struct_specifier` / `union_specifier`
  with bodies (with their `field_declaration` members), named
  `enum_specifier` (with enumerators as fields), `type_definition`
  (`typedef`), object and function-like `preproc_def` macros, and
  top-level `declaration` with an initializer. Function bodies are
  opaque so locals do not leak as script-level symbols.
  15 unit tests. Scheme `scip-c`. Files: `*.c`, `*.h`.
- `plugins/codemap-cpp/` — `tree-sitter-cpp` backed. Recurses through
  `namespace_definition` so descriptors carry the full namespace chain;
  unwraps `template_declaration` to surface the inner function or class.
  Captures `class_specifier` / `struct_specifier` / `union_specifier`
  (with `extra.cpp_kind`), `enum_specifier`, top-level and in-class
  `function_definition` (as `function` / `method`), and data-member
  `field_declaration`. 13 unit tests. Scheme `scip-cpp`. Files: `*.cpp`,
  `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx`.
- `plugins/codemap-csharp/` — `tree-sitter-c-sharp` backed.
  `namespace_declaration` is walked and dotted `qualified_name`
  (`App.Core.Util`) is split into individual NAMESPACE descriptors.
  Captures `class_declaration` / `interface_declaration` /
  `struct_declaration` / `record_declaration` / `enum_declaration` /
  `delegate_declaration` (all as `class` with distinguishing
  `extra.csharp_kind`), `method_declaration`, `property_declaration`,
  multi-declarator `field_declaration`, and `enum_member_declaration`.
  13 unit tests. Scheme `scip-csharp`. Files: `*.cs`, `*.csx`.
- `plugins/codemap-scala/` — `tree-sitter-scala` backed. Leading
  `package_clause` prefixes every symbol with NAMESPACE descriptors.
  Captures `class_definition` (including `case class` — with its
  `class_parameter`s emitted as fields), `object_definition`,
  `trait_definition`, top-level `type_definition`,
  `function_definition` / `function_declaration` (as methods), and
  `val_definition` / `var_definition` (as fields, tagged with
  `extra.scala_kind`). Nested members inside template bodies are
  scoped under the enclosing type. 13 unit tests. Scheme `scip-scala`.
  Files: `*.scala`, `*.sc`.
- `codemap doctor` now lists **15 indexers** (the four built-ins plus
  ten plugin-shipped grammars).

### Fixed — CI: `astral-sh/setup-uv@v3` fails without `uv.lock` (2026-05-30)

- Both `test.yml` and `bench.yml` workflows enabled `cache: true` on
  `setup-uv@v3`, which defaults its dependency glob to `**/uv.lock`.
  We don't commit a lockfile yet, so the action failed with
  *"No file in ... matched to [**/uv.lock]"* before any tests ran.
- Set `cache-dependency-glob: "pyproject.toml"` so the cache keys on a
  file that actually exists. No effect on local development.

### Added — SQL (DDL) and Bash independent PyPI plugins (2026-05-30)

- `plugins/codemap-sql/` — `tree-sitter-sql` backed. DDL only: emits
  `class` symbols for `CREATE TABLE` / `CREATE VIEW`, `variable`
  symbols for `CREATE INDEX`, and `field` symbols for each
  `column_definition` attached to the parent table.
  `SELECT`/`INSERT`/`UPDATE`/`DELETE` are intentionally ignored.
  13 unit tests. Scheme `scip-sql`. Files: `*.sql`, `*.ddl`.
- `plugins/codemap-bash/` — `tree-sitter-bash` backed. Captures
  `function_definition`, top-level `variable_assignment`, and
  `declaration_command` keywords (`readonly` / `declare` / `export` /
  `local` / `typeset`) tagged via `extra.bash_kind`. Function-internal
  state is deliberately not surfaced. Extensionless files with a bash
  shebang are also accepted via `supports()`. 14 unit tests. Scheme
  `scip-bash`. Files: `*.sh`, `*.bash`, `*.bats`.
- README (both languages) updated with the two new install commands,
  the bigger doctor table, and the longer indexer reference table.

### Added — Swift, Kotlin, Ruby, PHP independent PyPI plugins (2026-05-30)

- `plugins/codemap-swift/` — `tree-sitter-swift` backed. Class / struct /
  enum / protocol kept under `extra.swift_kind`; functions and `init`
  inside types become methods; top-level `let`/`var` become variables.
  14 unit tests. Scheme `scip-swift`.
- `plugins/codemap-kotlin/` — `tree-sitter-kotlin` backed. Class /
  interface / object under `extra.kotlin_kind`, package header captured
  as `extra.package`, `fun` inside type → method, top-level `val`/`var`
  → variable. Supports both `.kt` and `.kts`. 14 unit tests. Scheme
  `scip-kotlin`.
- `plugins/codemap-ruby/` — `tree-sitter-ruby` backed. Class / module
  under `extra.ruby_kind`, top-level `def` → function, `def` inside
  type → method, `def self.x` → method with `extra.ruby_kind=singleton`.
  Nested module/class produces qualified `Outer#Inner#m()` IDs. 13 unit
  tests. Scheme `scip-ruby`.
- `plugins/codemap-php/` — `tree-sitter-php` backed. Class / interface /
  trait / enum under `extra.php_kind`, `namespace_definition` captured
  as `extra.namespace`, method / property / const declarations inside
  types, free `function_definition` at module level, top-level `const`
  as variable. 13 unit tests. Scheme `scip-php`.
- README (both languages) updated with 4 new subdirectory install
  commands and the expanded doctor table (10 indexers total: 1
  reference + 9 language plugins).
- End-to-end smoke fixture: 9 User-class files across Java / Go / Rust /
  TypeScript / Python / Swift / Kotlin / Ruby / PHP indexed in one
  `codemap index` pass — 24 symbols across 9 SCIP schemes, 0
  diagnostics, both bridges executed.

### Added — Java, Go, Rust independent PyPI plugins (2026-05-30)

- `plugins/codemap-java/` — Java indexer backed by `tree-sitter-java`.
  Captures class / interface / enum / record / method / constructor /
  field declarations, honours `package` declarations as `extra.package`,
  and walks nested types via a class stack. SCIP scheme `scip-java`.
  14 unit tests.
- `plugins/codemap-go/` — Go indexer backed by `tree-sitter-go`.
  Captures function / method (receiver-aware) / struct / interface /
  type / const / var declarations. `func (u *User) Login()` produces
  `scip-go . . . main.go/User#Login().` so both value and pointer
  receivers feed into the same `User#…` namespace. 13 unit tests.
- `plugins/codemap-rust/` — Rust indexer backed by `tree-sitter-rust`.
  Captures free functions, methods inside `impl` (both inherent and
  `impl Trait for Type`) attached to the impl'd type, trait method
  signatures attached to the trait, plus struct / enum / trait / const /
  static items. SCIP scheme `scip-rust`. 13 unit tests.
- Each plugin ships with its own `pyproject.toml`, `README.md`,
  `src/codemap_<lang>/`, and `tests/`, depends only on `codemap +
  tree-sitter-<lang>`, and registers its indexer through the
  `codemap.indexers` entry-point group — identical mechanism to the
  built-in Python indexer and the previously shipped
  `codemap-typescript` plugin.
- README (both English and Simplified Chinese) updated with subdirectory
  install commands for all four language plugins and the updated
  `codemap doctor` indexer table.
- End-to-end smoke test on a 5-language fixture (Java + Go + Rust + TS +
  Python User class): 13 symbols emitted across 5 schemes, all bridges
  ran successfully, 0 diagnostics.

### Added — TypeScript indexer as an independent PyPI plugin (2026-05-30)

- New `plugins/codemap-typescript/` package: a fully independent
  Python distribution implementing the `Indexer` Protocol for
  TypeScript / TSX. Backed by `tree-sitter-typescript`. Recognises
  `function_declaration`, `class_declaration`, `interface_declaration`,
  `method_definition`, module-level `lexical_declaration` (const/let),
  and `import_statement`. SCIP scheme `scip-typescript`.
- The plugin lives in its own directory with its own `pyproject.toml`,
  `README.md`, `src/codemap_typescript/`, and tests. It declares one
  entry-point — `codemap.indexers.typescript = codemap_typescript:Type
  ScriptIndexer` — and that single line is the only coupling to the host
  CodeMap repo. After `pip install -e plugins/codemap-typescript/`,
  `codemap doctor` lists `typescript` next to the built-in `python` and
  `_example_lang` indexers on **identical terms** (ADR-004 + ADR-L001).
- 14 plugin-local unit tests cover the indexer's symbol generation,
  scheme consistency, TSX support, syntax-error and invalid-UTF8
  diagnostics, and the nested-class case.
- New `docs/plugin-guide.md` walks third-party authors through the
  process step by step using the TypeScript plugin as the reference.
- End-to-end smoke test against a sample TS + TSX project: 9 symbols
  emitted across function / class / interface / method / variable
  kinds; both `.ts` and `.tsx` file patterns work.

### Added — Incremental + watch (2026-05-30)

- `codemap index --incremental` compares each file's sha256 against the
  previous `manifest.files` entry and only re-parses changed files. Deleted
  files are removed; new files are picked up. Bridges re-run from scratch
  on every incremental pass via a new `JsonStore.clear_bridge_outputs()`
  helper so cross-module aliases / routes always reflect the current state.
- `codemap index --watch` keeps the process alive, runs an initial
  (incremental) pass, and re-indexes after every batch of file-system
  events (debounced 500 ms). Requires the `watchdog` extra
  (`pip install codemap[watch]`); the runtime check exits 69 (`EX_UNAVAILABLE`)
  with a friendly install hint when watchdog is missing.
- Watch mode ignores events under `.codemap/` to avoid feedback loops on
  its own writes.
- 7 e2e tests cover the no-op fast path, modified / deleted / new files,
  bridge re-evaluation after a rename, fallback to full when no prior
  index exists, and a real subprocess-based watch test that proves the
  watcher reacts to a live file change.

### Added — Cross-module Python call resolution (2026-05-30)

- New `codemap.core.bridge.python_cross_module.PythonCrossModuleBridge`
  resolves the synthetic `scip-python . . . <module>/<leaf>.` targets the
  Python indexer emits for cross-file imports. The bridge looks for a
  local symbol with the matching leaf name; if the file stem also matches
  the last namespace segment of the synthetic target the alias confidence
  is `high`, otherwise it falls back to `medium` for unambiguous single
  candidates and bails on ambiguity.
- `JsonStore.callers` / `callees` now transparently expand aliases via a
  reverse-alias index built at load time, so query commands automatically
  see cross-module callers without the caller doing anything special.
- On the CodeMap repo itself, `callers SymbolID#` now finds 10 callers
  across http_route.py / _example_lang.py / python.py / test_symbol.py
  rather than just the 1 same-file reference visible before.
- 10 unit tests + 3 e2e tests cover happy paths (file-stem match,
  single-candidate by leaf), explicit skips (no candidates, ambiguous
  candidates, non-python scheme, non-call edges, already-resolved
  targets, dedup), and the multi-file callers behaviour through the CLI.

### Added — Diagnostics command + error UX (2026-05-30)

- New `codemap diagnostics` command lists diagnostics recorded during the
  last `codemap index`. Filters: `--severity` (error/warning/info),
  `--producer` (indexer or bridge name), `--code` (e.g. `ROUTE001`),
  `--limit`. Both human and JSON outputs.
- Indexer crashes mid-file now become an `INDEXER_CRASH` diagnostic
  instead of being buried in stderr. Bridge crashes become
  `BRIDGE_CRASH`. Unreadable source files become `IO001`. The run
  completes either way.
- `codemap index --dry-run` walks the project and reports the per-indexer
  file counts without writing `.codemap/`.
- Friendly CLI exception wrapper: unhandled exceptions print a short
  marked-up "Internal error" message with the issue tracker URL and exit
  70 (`EX_SOFTWARE`). Set `CODEMAP_FULL_TRACEBACK=1` for the full
  traceback.

### Added — Configuration file (2026-05-30)

- `.codemap/config.yaml` now actually loads, replacing the previous empty
  placeholder. Three layers are merged in order: built-in defaults →
  `~/.config/codemap/config.yaml` → `<project>/.codemap/config.yaml`.
  Recursive mapping merge means each layer only has to mention what it
  changes.
- New schema (`codemap.config.schema.Config`, pydantic-backed,
  `extra=forbid` so typos surface as errors):
  - `storage.backend` (`json` | `sqlite`)
  - `index.ignore` (glob patterns on both file names and project-relative
    paths), `index.max_file_bytes`, `index.follow_symlinks`
  - `indexers.enabled` / `indexers.disabled`
  - `bridges.enabled` / `bridges.disabled`
- `codemap index` honours every field — `ignore` filters the walk,
  `max_file_bytes` replaces the previously hard-coded limit, and
  enabled/disabled lists shape which indexers / bridges run.
- New `codemap config show [--project P]` command prints the merged
  configuration (rendered YAML + source paths or a JSON envelope) so it's
  obvious which layer contributed which value.
- Validation errors surface as `EX_CONFIG` (exit 78) with the offending
  field path, never as a stack trace.
- 15 unit tests + 10 e2e tests cover schema defaults, layer merging,
  YAML errors, validation errors, ignore / max_file_bytes / disabled
  indexers / disabled bridges in action. `docs/configuration.md`
  documents every key.

### Added — Python HTTP recognition + benchmark gate (2026-05-30)

- **Python indexer** now produces `http_route` and `http_calls` metadata
  for the `http_route` bridge to consume — meaning the cross-language
  pipeline works end-to-end on real Python projects, not just synthetic
  fixtures. Recognises FastAPI-style verb decorators (`@app.get("/x")`),
  Flask-style `@route("/x", methods=[...])`, and `requests` / `httpx` /
  `aiohttp` / `urllib3` client calls. URL-like heuristic (`/` or `http(s)://`)
  filters out incidental `dict.get("key")` calls. 17 new unit tests cover
  the matrix; 4 e2e tests prove `codemap routes` and `codemap callers`
  surface the linked client→server graph after a single `codemap index`.
- **Benchmark suite** (`tests/bench/`) with `pytest-benchmark`, gated behind
  the `bench` marker so the default `pytest` run is unaffected. Six
  measurements: full-index throughput, callers / callees / search / walk /
  shortest_path. Targets are documented in `docs/performance.md`.
- **ADR-010 (benchmark regression gate)** flipped from Proposed to
  **Accepted**. Current baseline on the CodeMap repo: full-index 73 ms /
  callers 4.7 µs / callees 26 µs / walk depth-10 72 µs — every target from
  design §21 cleared by orders of magnitude. `.github/workflows/bench.yml`
  runs the suite on every PR and fails the build on ≥ 20 % median
  regression vs. main.

### Added — Query commands (2026-05-30)

- `codemap search QUERY` — keyword search across symbol IDs / signatures / docs.
- `codemap get <symbol-id>` — fetch one symbol's definition site, doc, and a
  source-line snippet. Exits 1 if not found, 64 (`EX_USAGE`) on malformed
  SymbolID, 66 (`EX_NOINPUT`) when `.codemap/` is missing.
- `codemap callers <symbol-id> [-d N]` — every edge whose target matches the
  given id (depth-limited).
- `codemap callees <symbol-id> [-d N]` — every edge whose source matches.
- `codemap trace --from <id> [--to <id>] [-d N]` — BFS downstream walk or
  bidirectional shortest-path between two symbols, with rich-tree text output
  and a structured JSON envelope.
- `codemap routes [--method M]` — list every HTTP route the `http_route`
  bridge has registered, with handler `file:line` references.
- `codemap.core.graph` — depth-limited downstream `walk_chain` and
  bidirectional `shortest_path` (capped per-side, so `-d N` finds paths up
  to `2N` hops).
- All commands accept `--project / -p`, support `--json`, and use the same
  exit-code conventions (ADR-005). 14 graph unit tests + 19 end-to-end CLI
  tests cover the new surface. `docs/cli.md` documents every command and its
  JSON shape.

### Added — Sprint M-1 — HTTP route bridge (2026-05-30)

- `codemap.core.bridge.http_route.HttpRouteBridge` — first cross-language
  Bridge. Reads `Symbol.extra["http_route"]` (server-side) and
  `Symbol.extra["http_calls"]` (client-side) metadata and emits
  `Route` / `Alias` / `Edge` entries pivoting on a synthetic
  `scip-route` intermediate symbol per `(method, path)`.
- Path-variable matching (`/user/{id}` ↔ `/user/42`), context-path
  prefix joining (`context_path` + `path` → `full_path`), and query-string
  stripping on the client URL.
- Diagnostics: `ROUTE001` for duplicate server handlers on the same route;
  `ROUTE002` for high-confidence client calls with no matching server
  route. Low-confidence (dynamic) client URLs do not warn.
- Tests: 21 unit cases (covering empty inputs, malformed metadata,
  path-variable matching, cross-language aggregation, etc.) plus 1
  integration test wiring the Bridge through a real `JsonStore` round
  trip on disk. `docs/bridges/http_route.md` documents the metadata
  contract and known limitations.
- Registered via `[project.entry-points."codemap.bridges"] http_route =
  "codemap.core.bridge.http_route:HttpRouteBridge"` — on equal footing
  with any third-party Bridge (ADR-004).

### Added — Sprint N-1 — Python indexer (2026-05-30)

- `codemap.indexers.python.PythonIndexer` — first real-language indexer.
  Built on the stdlib `ast` module; produces `function` / `method` /
  `class` / `field` / `variable` symbols and `calls` / `imports` /
  `extends` edges. Diagnostics are isolated per file (syntax errors,
  non-UTF-8 sources do not abort a run).
- SymbolID scheme `scip-python`; the file path is encoded as a chain of
  `namespace` descriptors, matching the SCIP convention.
- 25 unit cases + 3 golden directory fixtures under
  `tests/fixtures/indexers/python/`. Dogfood baseline on this repository:
  48 files / 437 symbols / 1232 edges / 0 diagnostics.
- `docs/indexers/python.md` documents the resolution policy, the
  confidence ladder, and known limitations.

### Changed

- `JsonStore` integrity check now treats only missing edge **sources** as
  corruption; missing edge **targets** are normal (external library
  references the indexer did not cover). Design doc §6.4 updated to
  match.

### Added — Sprint 0 — Engineering scaffolding (2026-05-30)

- Project layout following ADR-003 (`core` / `io` / `indexers` / `cli` / `mcp` separation).
- `pyproject.toml` (Hatch backend) with quality-gate configuration: ruff, mypy strict, pytest, coverage, import-linter.
- `SymbolID` (SCIP format) with parse / `to_string` round-trip — ADR-001.
- Pydantic data models with `schema_version` enforcement — ADR-006.
- `SymbolStore` Protocol + JSON backend with atomic writes and file locking — ADR-002, ADR-008.
- `Indexer` / `Bridge` Protocols with entry_points registry — ADR-004.
- Typer CLI skeleton: `--version`, `--help`, `doctor`, `index`.
- Diagnostics: sysexits.h exit codes, structured logging — ADR-005.
- CI: GitHub Actions matrix (Python 3.11/3.12/3.13 × macOS/Linux), lint + type + test + build.
- ADRs 0001–0012 documenting Day-1 decisions (including ADR-L001 language neutrality).
- Reference indexer `_example_lang` to validate end-to-end pipeline.

[Unreleased]: https://github.com/qxbyte/codemap/compare/v0.0.0...HEAD
