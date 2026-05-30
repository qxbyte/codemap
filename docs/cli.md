# CodeMap CLI reference

Every command supports ``--json`` for a machine-readable envelope and
defaults to a human-friendly ``rich``-rendered table. Project-scope
queries take ``--project / -p`` (default: ``.``); the project root must
contain a ``.codemap/`` directory built by ``codemap index``.

## Global flags

| Flag | Description |
|---|---|
| `--version` | Print version and exit. |
| `--json` | Emit a JSON envelope on stdout instead of a rendered table. The envelope shape is `{ "schema_version", "command", "result" }`. |
| `-v`, `-vv` | Raise log level to `INFO` / `DEBUG`. Logs go to stderr. |
| `--log-format text\|json` | Pick the log format for stderr. |
| `--help` | Show help for the command at hand. |

## Discovery

### `codemap doctor [PATH]`

Reports on registered indexers + bridges and on the local `.codemap/`
state. Exits 65 (`EX_DATAERR`) if the index is corrupted, 0 otherwise.

### `codemap index [PATH]`

Walks `PATH`, dispatches every file to the matching indexer(s), runs all
registered bridges, and writes `.codemap/` atomically.

| Flag | Description |
|---|---|
| `--rebuild` | Drop any existing `.codemap/` before indexing. |
| `--no-progress` | Suppress the progress bar. |

## Querying

### `codemap search QUERY [--limit N] [--project PATH]`

Substring match across symbol IDs, signatures, and docstrings. Returns at
most `N` hits (default 10), ranked by a simple heuristic.

```
$ codemap search login -n 3
kind     location                line  symbol
function src/auth/login.py:42    42    def login(user, password)
method   src/api/auth.py:18      18    def do_login(self, req)
...
```

### `codemap get <symbol-id> [--project PATH]`

Print one symbol's definition site + a one-line source snippet.

```
$ codemap get 'scip-python . . . src/auth/login.py/login().'
def login(user, password)
  kind:     function
  language: python
  location: src/auth/login.py:42

def login(user, password):
```

Exits non-zero if the symbol is not found; exits 64 (`EX_USAGE`) for an
unparseable SymbolID.

### `codemap callers <symbol-id> [--depth N] [--project PATH]`

Every edge whose **target** is `symbol-id`. `--depth` (default 1) walks
that many hops upstream.

### `codemap callees <symbol-id> [--depth N] [--project PATH]`

Mirror of `callers` — every edge whose **source** is `symbol-id`.

### `codemap trace --from <id> [--to <id>] [--depth N] [--project PATH]`

Two modes:

* **Walk** (no `--to`): BFS downstream from `--from`, capped at
  `--depth` hops. Output is a tree (`rich.tree`) or, with `--json`, a
  nested `{id, kind, file, line, incoming_edge, depth, children}` object.
* **Shortest-path** (`--from` + `--to`): bidirectional BFS through
  outgoing edges. With `--json`, the payload is `{from, to, found, path}`
  where `path` is a list of `{id, incoming_edge, …}` from start to end.

The `--depth` cap applies *per side* during bidirectional search, so a
value of `N` can find paths up to `2N` hops long.

### `codemap routes [--method METHOD] [--project PATH]`

Lists every HTTP route registered by the `http_route` bridge. With
`--method`, filters by HTTP method (case-insensitive). The table shows
`method`, `path`, and each handler's `file:line`.

```
$ codemap routes
method  path                  handler
GET     /api/users            src/server.py:42
GET     /api/user/{id}        src/server.py:58
POST    /api/user             src/server.py:71
```

## Exit codes

Standard `sysexits.h` (ADR-005):

| Code | Symbol | Meaning |
|---|---|---|
| 0 | — | OK |
| 64 | `EX_USAGE` | Bad CLI argument (e.g. malformed SymbolID) |
| 65 | `EX_DATAERR` | Index corruption, incompatible schema |
| 66 | `EX_NOINPUT` | No `.codemap/` at the project root |
| 70 | `EX_SOFTWARE` | Internal bug — please file an issue |
| 73 | `EX_CANTCREAT` | Cannot write `.codemap/` |
| 75 | `EX_TEMPFAIL` | Lock contention timeout |

## Output schemas

Every `--json` payload is a stable `{ schema_version, command, result }`
envelope. `result` shapes are documented inline above; they evolve under
SemVer and any change bumps `schema_version`.
