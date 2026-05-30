# codemap-kotlin

> A Kotlin indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-kotlin`:

| AST node | Symbol kind |
|---|---|
| `class_declaration` (keyword `class`) | `class` (with `extra.kotlin_kind=class`) |
| `class_declaration` (keyword `interface`) | `class` (with `extra.kotlin_kind=interface`) |
| `object_declaration` | `class` (with `extra.kotlin_kind=object`) |
| `function_declaration` (free) | `function` |
| `function_declaration` (inside type) | `method` |
| `property_declaration` (top-level) | `variable` |
| `property_declaration` (inside type) | `field` |

`package_header` is captured as `extra.package` on type symbols.

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-kotlin"
```

## SymbolID encoding

```
scip-kotlin . . . src/main/kotlin/User.kt/User#hello().
```

## Limits

* Companion object members are not attached to the enclosing class.
* Generic-parameter descriptors are dropped.

## License

MIT.
