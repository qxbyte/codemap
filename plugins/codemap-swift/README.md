# codemap-swift

> A Swift indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-swift`:

| AST node | Symbol kind |
|---|---|
| `class_declaration` (keyword `class`) | `class` (with `extra.swift_kind=class`) |
| `class_declaration` (keyword `struct`) | `class` (with `extra.swift_kind=struct`) |
| `class_declaration` (keyword `enum`) | `class` (with `extra.swift_kind=enum`) |
| `protocol_declaration` | `class` (with `extra.swift_kind=protocol`) |
| `function_declaration` | `function` (free) or `method` (inside type) |
| `init_declaration` | `method` (signature prefixed with `init`) |
| `property_declaration` (top-level) | `variable` |
| `property_declaration` (inside type) | `field` |

## Install

```bash
pip install codemap-swift
```

## SymbolID encoding

```
scip-swift . . . src/User.swift/User#hello().
```

## Limits

* Extensions (`extension User { ... }`) are not yet tracked.
* Generic-parameter descriptors are dropped.
* Property wrappers are ignored.

## License

MIT.
