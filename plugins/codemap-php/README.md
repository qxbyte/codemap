# codemap-php

> A PHP indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-php`:

| AST node | Symbol kind |
|---|---|
| `class_declaration` | `class` (with `extra.php_kind=class`) |
| `interface_declaration` | `class` (with `extra.php_kind=interface`) |
| `trait_declaration` | `class` (with `extra.php_kind=trait`) |
| `enum_declaration` | `class` (with `extra.php_kind=enum`) |
| `method_declaration` (inside type) | `method` |
| `function_definition` (top level) | `function` |
| `property_declaration` (inside type) | `field` |
| `const_declaration` (top level) | `variable` |
| `const_declaration` (inside type) | `field` |

`namespace_definition` is captured as `extra.namespace` on every
symbol-producing type.

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-php"
```

## SymbolID encoding

```
scip-php . . . src/App/User.php/User#hello().
```

## Limits

* Use statements aren't yet expanded into namespace-resolved edges.
* PHPDoc annotations are not parsed.
* Anonymous classes are skipped.

## License

MIT.
