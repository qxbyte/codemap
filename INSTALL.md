# Installation Guide

**English** · [简体中文](./INSTALL.zh-CN.md)

> As of **0.3.1** (2026-06-25), CodeMap is published to PyPI under the
> distribution names `codemap-core` (main), `codemap-<lang>` (17
> language plugins), and `codemap-mybatis` / `codemap-aimemory` (new
> in 0.3.0 — framework awareness + four-layer memory model L1 output).
> 0.3.1 adds the `codemap llm config` CLI for persisting LLM api-key /
> base-url, plus a docs section on Chinese / open-source LLM endpoints.
> The instructions below use PyPI as the primary
> install source; the [Install from git](#28-install-from-git-track-main-pin-to-a-commit)
> section retains the older `git+https://…` form for users who need to
> track `main` or pin to a specific commit. The
> [Validation log](#7-validation-log) at the end is a verbatim
> transcript from the pre-release 2026-05-30 run against
> [`qxbyte/codemap@c4cd436`](https://github.com/qxbyte/codemap/commit/c4cd436);
> the commands and numbers there are accurate but use the older
> `git+https://…` install URL.

---

## Table of contents

- [TL;DR](#tldr)
- [1. Requirements](#1-requirements)
- [2. Install the main CLI](#2-install-the-main-cli)
  - [2.8 Install from git](#28-install-from-git-track-main-pin-to-a-commit)
- [3. Verify](#3-verify)
- [4. Add language plugins](#4-add-language-plugins)
  - [4.6 From git](#46-from-git-track-main-pin-to-a-commit)
- [5. First-time usage](#5-first-time-usage)
- [6. Upgrade and uninstall](#6-upgrade-and-uninstall)
- [7. Validation log](#7-validation-log)
- [8. Offline distribution](#8-offline-distribution)
- [9. Troubleshooting](#9-troubleshooting)

---

## TL;DR

```bash
# 1. Install pipx (one-time, system-wide)
brew install pipx && pipx ensurepath          # macOS
# or:  python3 -m pip install --user pipx && pipx ensurepath  (Linux)

# 2. Install the main CLI from PyPI
pipx install codemap-core

# 3. Inject any language plugins you need
pipx inject codemap codemap-java

# 4. Use it
cd ~/your-project
codemap index .
codemap doctor
codemap routes
```

That's it. The rest of this document is a longer explanation of the
same steps and the alternative install paths.

---

## 1. Requirements

| Item | Requirement | Notes |
|---|---|---|
| Python | **≥ 3.11** | Development happens on 3.13. macOS' system `python3` is often 3.9 — install a newer one before continuing. |
| OS | macOS / Linux | Windows works for indexing; `--watch` falls back to polling. |
| Network | Required **only at install time** | To clone the repo and fetch `tree-sitter-*` binary wheels. The index itself runs fully offline. |
| Disk | ~30 MB main CLI + ~1–5 MB per language plugin | Negligible. |

Check your Python:

```bash
python3 --version
# If this prints anything below 3.11, install a newer Python first:
#   macOS:  brew install python@3.12
#   Linux:  use your package manager (apt install python3.12, etc.)
#   Cross-platform:  pyenv install 3.12.7 / uv python install 3.12
```

---

## 2. Install the main CLI

CodeMap is published on PyPI as `codemap-core`. Pick one of three
install paths:

### 2.1 With `pipx` (recommended)

`pipx` isolates each tool in its own virtualenv and puts the
`codemap` command on your `$PATH` — exactly what you want for a CLI.

```bash
pipx install codemap-core
```

### 2.2 With `uv tool`

Same isolation model as `pipx`, but faster:

```bash
uv tool install codemap-core
```

### 2.3 With plain `pip` (not recommended)

Pollutes whatever environment is active. Use only inside a virtualenv
you fully control:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install codemap-core
```

### 2.4 Optional extras

```bash
# `codemap index --watch` needs watchdog
pipx install "codemap-core[watch]"

# Development tooling (pytest, ruff, mypy, import-linter, pytest-benchmark)
pipx install "codemap-core[dev]"
```

### 2.5 Pin to an exact version

```bash
pipx install "codemap-core==0.1.0"
```

### 2.6 Pre-releases (alpha / beta / rc)

`pipx` skips pre-releases by default. Use `--pip-args="--pre"` to opt
in:

```bash
pipx install --pip-args="--pre" codemap-core
```

### 2.7 Upgrade

```bash
pipx upgrade codemap                  # injected plugins follow automatically
uv tool upgrade codemap               # uv equivalent
pip install --upgrade codemap-core    # plain pip inside a venv
```

### 2.8 Install from git (track `main`, pin to a commit)

For users who want unreleased changes from `main` or to pin to a
specific commit before the next PyPI release, the git URL form still
works:

```bash
# Track main
pipx install git+https://github.com/qxbyte/codemap.git
pip install git+https://github.com/qxbyte/codemap.git

# Pin to a commit
pipx install "git+https://github.com/qxbyte/codemap.git@<commit-sha>"

# Specific extras
pipx install "git+https://github.com/qxbyte/codemap.git#egg=codemap[watch]"
```

---

## 3. Verify

```bash
codemap --version
# → 0.1.0

codemap --help        # global flags and subcommand list

cd /tmp/empty-dir     # any directory without a .codemap/
codemap doctor
```

A clean install (no language plugins yet) shows **2 indexers** and
**2 bridges**:

```
                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │

             Registered bridges
┃ name                ┃ version ┃ requires ┃
│ http_route          │ 0.1.0   │ -        │
│ python_cross_module │ 0.1.0   │ -        │
```

> `_example_lang` is a reference implementation for plugin authors —
> it parses `*.example` files and exists primarily to keep the plugin
> contract honest. You can ignore it in real use.

---

## 4. Add language plugins

Each non-Python language indexer ships as an **independent PyPI
package** under `plugins/`. Installing one adds its grammar; it's
auto-discovered via `entry_points` — no configuration files to edit.

### 4.1 Available plugins

| Language | Subdirectory | File patterns | Backed by |
|---|---|---|---|
| TypeScript / TSX | `plugins/codemap-typescript` | `*.ts`, `*.tsx` | `tree-sitter-typescript` |
| Java | `plugins/codemap-java` | `*.java` | `tree-sitter-java` |
| Go | `plugins/codemap-go` | `*.go` | `tree-sitter-go` |
| Rust | `plugins/codemap-rust` | `*.rs` | `tree-sitter-rust` |
| Swift | `plugins/codemap-swift` | `*.swift` | `tree-sitter-swift` |
| Kotlin | `plugins/codemap-kotlin` | `*.kt`, `*.kts` | `tree-sitter-kotlin` |
| Ruby | `plugins/codemap-ruby` | `*.rb` | `tree-sitter-ruby` |
| PHP | `plugins/codemap-php` | `*.php` | `tree-sitter-php` |
| SQL (DDL) | `plugins/codemap-sql` | `*.sql`, `*.ddl` | `tree-sitter-sql` |
| Bash | `plugins/codemap-bash` | `*.sh`, `*.bash`, `*.bats` | `tree-sitter-bash` |
| C | `plugins/codemap-c` | `*.c`, `*.h` | `tree-sitter-c` |
| C++ | `plugins/codemap-cpp` | `*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx` | `tree-sitter-cpp` |
| C# | `plugins/codemap-csharp` | `*.cs`, `*.csx` | `tree-sitter-c-sharp` |
| Scala | `plugins/codemap-scala` | `*.scala`, `*.sc` | `tree-sitter-scala` |

### 4.1b Framework / output plugins (new in 0.3.0)

| Purpose | Distribution | What it adds |
|---|---|---|
| MyBatis Mapper XML | `codemap-mybatis` | Parses `*Mapper.xml`, emits `sql_mapping` symbols + `table` symbols + `accesses_table` edges (DML side); a `MyBatisLinkBridge` produces `maps_to` edges from Java Mapper interface methods to their backing XML statements. Requires `codemap-java` to resolve the Java side. |
| `.ai-memory/` emitter | `codemap-aimemory` | Emits the four-layer memory model's L1 layout (`entities/*.yml` + `relations/*.yml`) so AI agents can consume the index directly. Includes an optional `enrich()` overlay that calls an injected `LlmClient` to fill `business_meaning` / `related_rules` — entirely opt-in, the core index never depends on an LLM. Install with `[llm]` extra to pull `anthropic` for the SDK shape. |

### 4.2 With `pipx inject` (recommended)

`pipx inject` puts the plugin into the same isolated environment as
the main CLI:

```bash
# All 17 languages in a single command
pipx inject codemap codemap-typescript codemap-javascript codemap-vue \
                    codemap-java codemap-jsp codemap-go \
                    codemap-rust codemap-swift codemap-kotlin \
                    codemap-ruby codemap-php codemap-sql \
                    codemap-bash codemap-c codemap-cpp \
                    codemap-csharp codemap-scala

# Framework awareness + .ai-memory output (new in 0.3.0, opt-in)
pipx inject codemap codemap-mybatis codemap-aimemory

# Or one at a time
pipx inject codemap codemap-typescript
```

### 4.3 With `uv tool inject`

```bash
uv tool inject codemap codemap-java
```

### 4.4 With plain `pip`

If you installed via `pip` into an active virtualenv, install plugins
the same way:

```bash
pip install codemap-java
```

### 4.6 From git (track `main`, pin to a commit)

If you need an unreleased plugin from `main` or a specific commit, fall
back to the subdirectory URL form:

```bash
pipx inject codemap "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
```

### 4.5 Verify the plugin was picked up

```bash
codemap doctor
```

Every newly installed plugin should appear in the **Registered
indexers** table without any further configuration. If you don't see
it, jump to [Troubleshooting](#9-troubleshooting).

### 4.7 AI-Enterprise-Delivery-System workflow plugins (optional)

codemap is the **code-side** half of a four-layer-memory-model
workflow. The **spec / execution / knowledge-distillation** halves
live in a separate plugin family at
[`pluginhub`](https://github.com/qxbyte/pluginhub). They are entirely
optional — codemap runs fully standalone — but install them when you
want the full closed loop:

```
new requirement
   ↓ specode → requirements / design / execute / acceptance
   ↓ task-swarm (multi-agent parallel execution)
   ↓ specode-distill (knowledge written to <project_root>/.ai-memory/knowledge/ + knowledge-base/)
   ↓ next requirement → codemap recall pulls prior knowledge → injected into new spec
```

The three pluginhub plugins are installed through your AI IDE's plugin
manager (Claude Code shown here; Codex / Copilot CLI follow the same
pattern):

```
# in Claude Code
/plugin marketplace add github:qxbyte/pluginhub
/plugin install specode      # spec workflow + specode-distill sub-skill
/plugin install task-swarm   # multi-agent pipeline orchestration

# optional: superpowers — brainstorming / writing-plans / TDD; specode prefers it
/plugin marketplace add github:obra/superpowers-marketplace
/plugin install superpowers
```

| Plugin | Min version | Writes to `<project_root>/` | When |
|---|---|---|---|
| `specode` | **3.3.1** | (only via specode-distill sub-skill below) | drives the spec lifecycle; requires codemap-aimemory 0.4.3+ for step-2.2 content injection (FIX-2 `codemap knowledge write` rewire); 3.3.1 also surfaces project-level agent docs (CLAUDE.md / AGENT.md / AGENTS.md / CODEBUDDY.md) into requirements.md (AI-EDS v0.9 痛点 #14 方案 D) |
| └─ `specode-distill` | (sub-skill of specode 3.0+) | `.ai-memory/knowledge/{rules,business,modules,cases,pitfalls}/*.yml` + `knowledge-base/*.md` (twin) | user runs `/specode:specode-distill <slug>`, or accepts the prompt at end of specode's acceptance phase |
| `task-swarm` | **0.7.3** | `.ai-memory/knowledge/{cases,pitfalls}/*.yml` + `knowledge-base/*.md` (twin, written via `codemap knowledge write` since 0.7.0 / FIX-2) | every successful `task_swarm.py resolve`; 0.7.3 also inserts a `## 项目级约束（必读）` section into every coder / reviewer / validator `task.md` (痛点 #14 方案 D) |
| `superpowers` | any | — (no `.ai-memory/` writes) | brainstorming / writing-plans skills called by specode |

After install, the new slash commands:

| Plugin | Commands |
|---|---|
| specode | `/specode:specode-spec`, `/specode:specode-continue`, `/specode:specode-list`, `/specode:specode-distill` |
| task-swarm | `/task-swarm:swarm` |

specode 2.1+ calls **`codemap recall`** (from `codemap-aimemory`,
PyPI) inside its requirements phase to pull prior knowledge before
drafting a new spec. So if you want the full integration:

```bash
# Make sure codemap-aimemory is installed (it ships `codemap recall`)
pipx inject codemap codemap-aimemory   # if not already done in §4.2

# Verify recall is available
codemap recall --help                  # should print usage
```

Without `codemap-aimemory`, the spec workflow still runs — specode's
context-recall step just becomes a silent no-op.

The pluginhub plugin family has its own product line of Obsidian-vault
maintenance tools (`obsidian-wiki` 2.0+). It is **NOT** part of the
AI-EDS workflow — install it only if you also want to maintain an
Obsidian LLM-wiki separately.

---

## 5. First-time usage

```bash
cd /path/to/your-project

# Build the index (writes ./.codemap/)
codemap index .

# Inspect the index
codemap doctor                        # plugin + index health
codemap diagnostics --severity error  # parser warnings / errors, if any

# Search
codemap search login -n 5
codemap get '<symbol-id>'             # source snippet for a single symbol
codemap callers '<symbol-id>'         # who calls this
codemap callees '<symbol-id>'         # what does this call
codemap trace --from '<id>' --depth 5
codemap routes                        # all HTTP routes the http_route bridge found

# Knowledge recall (requires codemap-aimemory plugin, 0.3.5+; 0.4.0+ for --with-content)
# Scans .ai-memory/knowledge/*.yml — written by specode-distill /
# task-swarm if you've installed the pluginhub workflow (see §4.7).
codemap recall '<query>'                   # default top-k 5, yaml
codemap recall '<query>' -k 10 -o json
codemap recall '<query>' -t rules,pitfalls
codemap recall --from-spec requirements.md # 0.3.6+: spec file as query
codemap recall '<query>' --with-content    # 0.4.0+: include rule/pit/case core fields
# Each hit since 0.4.0 carries freshness_score / ranked_score / stale —
# fresher knowledge outranks stale at the same token score.

# Semantic recall (opt-in, requires codemap-semantic-index 0.1.0+)
pipx inject codemap codemap-semantic-index   # pulls sentence-transformers + torch

# ⚠️ If you're in mainland China (or any restricted-egress network),
# set the HuggingFace mirror + token before the first embed run —
# direct connection to huggingface.co often times out / hangs at 0 bytes.
# Register at https://huggingface.co/ → Settings → Access Tokens → create Read token
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.zshrc   # CN mirror
echo 'export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx' >> ~/.zshrc  # your token, never share
source ~/.zshrc

codemap embed install                         # interactive picker, default Qwen3-Embedding-0.6B (1.2GB)
codemap embed                                  # incremental embed of knowledge-base/*.md
codemap embed backend set --provider qwen --api-key sk-xxx  # OR switch to cloud (no model download)
# After this, `codemap recall` automatically does hybrid token+embedding ranking
# (RRF fusion) — no extra flag needed.

# Machine-readable output for AI agents
codemap --json routes
codemap --json callers '<symbol-id>'
```

Re-indexing later:

```bash
codemap index . --incremental         # re-parse only files whose sha256 changed
codemap index . --watch               # daemon mode (requires the [watch] extra)
codemap index . --rebuild             # discard everything and start over
codemap index . --dry-run             # report what would be indexed, no writes
```

Configuration lives in `.codemap/config.yaml` (project-local) and
`~/.config/codemap/config.yaml` (user-global). See
[`docs/configuration.md`](docs/configuration.md) for the full schema.

---

## 6. Upgrade and uninstall

### Upgrade

```bash
pipx upgrade codemap                  # pulls the latest main; injected plugins follow
uv tool upgrade codemap               # uv equivalent
```

To upgrade to a specific commit:

```bash
pipx uninstall codemap
pipx install "git+https://github.com/qxbyte/codemap.git@<commit-sha>"
# then re-inject your plugins
```

### Uninstall

```bash
pipx uninstall codemap                # removes the CLI and every injected plugin
uv tool uninstall codemap             # uv equivalent
```

The local `.codemap/` directory in each project is independent — delete
it manually if you want a project to forget its index.

---

## 7. Validation log

The following is a verbatim transcript of a clean-machine install run
performed on **2026-05-30** against
[`qxbyte/codemap@c4cd436`](https://github.com/qxbyte/codemap/commit/c4cd436).
Every number and table below is what the commands actually produced.

### 7.1 Environment

```bash
$ python3.12 -m venv /tmp/codemap-fresh
$ /tmp/codemap-fresh/bin/python --version
Python 3.12.13
```

### 7.2 Install the CLI (≈ 2 minutes)

```bash
$ time /tmp/codemap-fresh/bin/pip install "git+https://github.com/qxbyte/codemap.git"
...
Successfully installed annotated-doc-0.0.4 annotated-types-0.7.0
  codemap-0.1.0 markdown-it-py-4.2.0 mdurl-0.1.2 pydantic-2.13.4
  pydantic-core-2.46.4 pygments-2.20.0 pyyaml-6.0.3 rich-15.0.0
  shellingham-1.5.4 typer-0.26.3 typing-extensions-4.15.0
  typing-inspection-0.4.2

pip install  2.36s user  1.00s system  2% cpu  2:05.55 total
```

### 7.3 Verify (sub-second)

```bash
$ /tmp/codemap-fresh/bin/codemap --version
0.1.0

$ cd /tmp/codemap-demo-project   # empty dir
$ /tmp/codemap-fresh/bin/codemap doctor
CodeMap 0.1.0
project_root: /private/tmp/codemap-demo-project

                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │

             Registered bridges
┃ name                ┃ version ┃ requires ┃
│ http_route          │ 0.1.0   │ -        │
│ python_cross_module │ 0.1.0   │ -        │

No `.codemap/` directory found. Run `codemap index` to build one.
```

### 7.4 Inject a language plugin (≈ 16 seconds)

```bash
$ time /tmp/codemap-fresh/bin/pip install \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
...
Successfully installed codemap-java-0.1.0 tree-sitter-0.25.2 tree-sitter-java-0.23.5

pip install  0.75s user  0.41s system  7% cpu  15.608 total
```

```bash
$ /tmp/codemap-fresh/bin/codemap doctor | head -10
                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ java          │ 0.1.0   │ java      │ *.java        │   ← auto-discovered
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │
```

### 7.5 Index a mixed Java + Python project

A fixture with one `User.java` (a class with a `greet()` method) and
one `app.py` (a Flask app with `@app.route("/users/<int:uid>")`):

```bash
$ /tmp/codemap-fresh/bin/codemap index .
Indexed 2 files
┃ metric        ┃ count ┃
│ files_scanned │ 2     │
│ files_indexed │ 2     │
│ symbols       │ 6     │
│ edges         │ 1     │
│ routes        │ 1     │
│ diagnostics   │ 0     │
│ bridges_run   │ 2     │
```

Search and route lookup:

```bash
$ /tmp/codemap-fresh/bin/codemap search greet
┃ kind   ┃ location    ┃ symbol         ┃
│ method │ User.java:5 │ String greet() │

$ /tmp/codemap-fresh/bin/codemap routes
┃ method ┃ path             ┃ handler  ┃
│ GET    │ /users/<int:uid> │ app.py:5 │
```

JSON mode:

```bash
$ /tmp/codemap-fresh/bin/codemap --json routes
{
  "schema_version": "1.0.0",
  "command": "routes",
  "result": {
    "method_filter": null,
    "results": [
      {
        "method": "GET",
        "path": "/users/<int:uid>",
        "route_id": "scip-route . . . api/GET#`/users/<int:uid>`.",
        "handlers": [
          { "id": "scip-python . . . app.py/get_user().",
            "kind": "function", "language": "python",
            "file": "app.py", "line": 5 }
        ]
      }
    ]
  }
}
```

### 7.6 What this confirms

- The main CLI ships **no language bias** — only `python` and the
  `_example_lang` reference; everything else is opt-in via plugins.
- Plugins are **zero-config**: a `pip install` is the only step;
  no entry registered or config edited.
- The `http_route` bridge already works across languages on the first
  index — the Flask decorator becomes a `scip-route` symbol that a
  Java caller (in a hypothetical mixed-stack repo) could be linked to
  through the same SymbolID format.
- `--json` output is stable enough to feed an AI agent directly.

---

## 8. Offline distribution

If the target machine has no network at install time, build a wheel
bundle on a connected machine:

```bash
# On the source machine (has network)
mkdir codemap-offline && cd codemap-offline
pip download \
    "git+https://github.com/qxbyte/codemap.git" \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java" \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-typescript" \
    -d ./wheels

# Tar it and copy to the target machine
tar czf codemap-offline.tar.gz wheels/

# On the target machine
tar xzf codemap-offline.tar.gz
python3.12 -m venv /opt/codemap
/opt/codemap/bin/pip install --no-index --find-links=./wheels codemap codemap-java codemap-typescript
ln -sf /opt/codemap/bin/codemap /usr/local/bin/codemap
```

`pip download` resolves and downloads every transitive wheel,
including platform-specific `tree-sitter-*` artifacts. Use the **same
Python major/minor and the same OS/CPU** on both ends.

---

## 9. Troubleshooting

### "python3 --version says 3.9.x"

macOS ships an old system Python. Install a newer one and use it
explicitly:

```bash
brew install python@3.12
python3.12 -m venv .venv      # use it directly
# or use pyenv / uv / mise to manage versions
```

### "command not found: codemap"

After `pipx install`, run `pipx ensurepath` once and **open a new
shell** so the updated `$PATH` is picked up. To verify the actual
location:

```bash
pipx list                     # shows installed apps and their paths
ls ~/.local/bin/codemap       # the symlink pipx creates
```

### "I installed a plugin but `doctor` doesn't show it"

The plugin must be installed into **the same environment as the CLI**.

- `pipx`: use `pipx inject codemap <plugin>` — **not** `pip install`
  in your shell, which goes to a different environment.
- `uv tool`: use `uv tool inject codemap <plugin>`.
- Virtualenv: activate it (`source .venv/bin/activate`) before
  `pip install`.

Verify which Python ships the CLI:

```bash
which codemap
head -1 $(which codemap)      # the shebang points at the right Python
```

### "Install took >2 minutes / timed out"

`pip install` from GitHub clones the repo (≈ 5 MB) and may build
`tree-sitter-*` from source on first run. Subsequent installs use
the wheel cache.

For very slow networks, build wheels once with `pip wheel` and reuse
them across machines (see [Offline distribution](#8-offline-distribution)).

### "`doctor` shows a `.codemap/` from somewhere I didn't expect"

CodeMap walks upward from the current directory looking for the
nearest `.codemap/` to use as the project root. Either `cd` into the
project root before running, or pass an explicit path:

```bash
codemap index /path/to/project        # absolute path
```

### "tree-sitter-X build fails on first install"

On Apple Silicon some grammars (especially `tree-sitter-rust`,
`tree-sitter-cpp`) take 30 s – 1 min to compile and need the Xcode
command-line tools:

```bash
xcode-select --install
```

On Linux you may need a C compiler and Python development headers:

```bash
sudo apt install build-essential python3-dev          # Debian/Ubuntu
sudo dnf install gcc python3-devel                    # Fedora
```

### "I want to remove only one plugin, not the whole CLI"

```bash
pipx runpip codemap uninstall codemap-java            # pipx
uv tool uninstall-from codemap codemap-java           # uv
pip uninstall codemap-java                            # plain pip
```

Then run `codemap doctor` to confirm it's gone.

---

If something still isn't working, please open an issue at
<https://github.com/qxbyte/codemap/issues> with the exact `codemap
doctor` output and the install command you used.
