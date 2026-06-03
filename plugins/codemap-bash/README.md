# codemap-bash

> A Bash / shell-script indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-bash`:

| AST node | Symbol kind |
|---|---|
| `function_definition` | `function` |
| Top-level `variable_assignment` | `variable` |
| `declaration_command` (`readonly`/`declare`/`export`/`local`) at top level | `variable` (with `extra.bash_kind=<keyword>`) |

Function bodies are **not** walked for inner assignments — anything
declared inside a function is local state, not a script-level symbol.

## Install

```bash
pip install codemap-bash
```

## SymbolID encoding

```
scip-bash . . . scripts/deploy.sh/greet().
scip-bash . . . scripts/deploy.sh/MAX_RETRIES.
```

## File patterns

* `*.sh`, `*.bash`, `*.bats`
* Files without an extension whose shebang starts with `#!/bin/bash` or
  `#!/usr/bin/env bash` are matched via `supports()`.

## Limits

* `source` / `.` includes are not turned into edges.
* Aliases (`alias ll='ls -la'`) are not captured.
* `getopts` argument schemas aren't structured.
* POSIX sh / Zsh / Fish dialects parse, but constructs unique to them
  may degrade to syntax-error diagnostics.

## License

MIT.
