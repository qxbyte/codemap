# Configuration

CodeMap reads `config.yaml` from up to three layers, merged in this order:

1. **Built-in defaults** — every field has a sensible value, so a totally
   absent config still produces a working `codemap index`.
2. **User-level**: `~/.config/codemap/config.yaml`. Per-machine preferences.
3. **Project-level**: `<project>/.codemap/config.yaml`. Per-repo settings,
   typically committed alongside source.

Later layers override earlier ones. Within nested mappings the merge is
recursive (so a project file that touches only `index.ignore` still
inherits everything else from the user layer + defaults).

CLI flags (`--no-progress`, `--rebuild`, …) sit above all three layers and
win on conflict.

## Quick reference

```yaml
# .codemap/config.yaml

storage:
  backend: json        # json | sqlite

index:
  ignore: []           # extra glob patterns (file names + project-relative paths)
  max_file_bytes: 10485760   # skip files larger than this (default 10 MB)
  follow_symlinks: false

indexers:
  enabled: all         # "all" or an explicit list of indexer names
  disabled: []         # subtractive — applied AFTER `enabled`

bridges:
  enabled: all
  disabled: []
```

## Sections

### `storage`

* **backend** (default `json`): persistence backend. Currently `json` is
  the only one implemented; `sqlite` is reserved for the Sprint Y backend
  swap (see ADR-002).

### `index`

* **ignore** (default `[]`): a list of `fnmatch` patterns. Each pattern
  is matched against (a) every file name and (b) every project-relative
  POSIX path during the walk. Examples:
  ```yaml
  index:
    ignore:
      - "*.bak"           # skip *.bak everywhere
      - "vendor"          # skip top-level (or nested) ``vendor`` dirs
      - "**/generated/**" # skip anything under any ``generated`` directory
  ```
  Universally noisy directories (`.git`, `node_modules`, `.venv`,
  `__pycache__`, `dist`, …) are pruned even without listing them here.
* **max_file_bytes** (default 10 MiB): files larger than this are
  skipped to keep the indexer responsive. Increase if your project has
  generated single-file blobs you want indexed.
* **follow_symlinks** (default `false`): if `true`, `os.walk` follows
  symbolic links. Cycle-safe but can balloon the file count; leave off
  unless you actually rely on linked sources.

### `indexers`

* **enabled** (default `"all"`): either the literal string `"all"` or an
  explicit list of indexer names (`["python", "typescript"]`). Names that
  don't match a registered indexer are silently ignored — a stale config
  on a fresh machine still works.
* **disabled** (default `[]`): subtractive list applied *after* `enabled`.
  Typical entry: `"_example_lang"` to keep the reference indexer out of a
  real index.

### `bridges`

Same `enabled` / `disabled` shape as `indexers`. Useful to turn off the
`http_route` bridge on services that don't expose HTTP at all.

## Inspecting the effective config

```bash
$ codemap config show           # rendered YAML + source paths
$ codemap --json config show    # machine-readable envelope
```

Both forms also list the source paths (and whether they exist) so it's
easy to tell which layer a given value came from.

## Validation

Every key is validated against a pydantic schema. Unknown keys are
treated as errors (typos surface immediately, deprecated keys can't sit
silently). On failure the command exits 78 (`EX_CONFIG`) with a message
that names the offending field path:

```
$ codemap index .
Config error: config validation failed:
  - storage.backend: Input should be 'json' or 'sqlite'
```
