# codemap-typescript

> A TypeScript / TSX indexer for [CodeMap](https://github.com/qxbyte/codemap),
> distributed as an independent PyPI package.

## What this package proves

**Adding a new language to CodeMap doesn't require touching the main
repository.** This package implements the `codemap.indexers.base.Indexer`
Protocol against `*.ts` / `*.tsx` files and registers through the
`codemap.indexers` entry-point group. Once installed it appears in
`codemap doctor` next to the built-in indexers, on completely equal
footing (ADR-004 + ADR-L001).

```text
$ pip install codemap-typescript
$ codemap doctor
Registered indexers
┏━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ name          ┃ version ┃ languages  ┃ file_patterns ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ _example_lang │ 0.1.0   │ example    │ *.example     │
│ python        │ 0.1.0   │ python     │ *.py, *.pyi   │
│ typescript    │ 0.1.0   │ typescript │ *.ts, *.tsx   │
└───────────────┴─────────┴────────────┴───────────────┘
```

`codemap.indexers.disabled: ["typescript"]` in `.codemap/config.yaml` turns
it off without uninstalling.

## What it captures

Backed by `tree-sitter-typescript`. Single-file, no cross-file type
inference (MVP):

| AST node | Symbol kind | SymbolID descriptor |
|---|---|---|
| `function_declaration` | `function` | `<path>/name().` |
| `class_declaration` | `class` | `<path>/Cls#` |
| `interface_declaration` | `interface` | `<path>/Cls#` |
| `method_definition` (inside class) | `method` | `<path>/Cls#name().` |
| `lexical_declaration` (top-level `const`/`let`) | `variable` | `<path>/Name.` |

Edges:

* `import_statement` / `import_from_clause` → `imports` to a synthetic
  module symbol (consumed by the same bridges the Python indexer drives).

The matcher is intentionally lean — class inheritance, generic
constraints, and decorators are not yet captured. The point is that they
*can* be: a v0.2.0 PR to this repository is enough to extend coverage,
the main CodeMap repository stays untouched.

## SymbolID encoding

```
scip-typescript . . . src/app/Service.ts/UserService#login().
└──────────────┘ └──────────────────────────────────┘
     scheme               file → namespaces / type / method
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Limits / next steps

* No cross-file `import` resolution. The main `python_cross_module`
  bridge has a sibling for Python; a `typescript_cross_module` bridge
  could be added in a future release.
* No JSX-specific patterns (component declarations) yet.
* `interface_declaration` is captured as `class` kind — CodeMap's symbol
  schema doesn't yet have a distinct `interface` kind, see design §3.3.

## License

MIT — same as the host project.
