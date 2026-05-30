# codemap-ruby

> A Ruby indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-ruby`:

| AST node | Symbol kind |
|---|---|
| `class` | `class` (with `extra.ruby_kind=class`) |
| `module` | `class` (with `extra.ruby_kind=module`) |
| `method` (inside class/module) | `method` |
| `method` (top level) | `function` |
| `singleton_method` | `method` (with `extra.ruby_kind=singleton`) |
| top-level constant `assignment` | `variable` |
| constant assignment inside class/module | `field` |

Nested class / module declarations are tracked with a class stack:
`module A; class B; def m; end; end; end` produces `A#B#m()`.

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-ruby"
```

## SymbolID encoding

```
scip-ruby . . . app/models/user.rb/User#hello().
```

## Limits

* `attr_accessor` / `attr_reader` / `attr_writer` macros are not
  expanded into individual field symbols.
* `define_method`, `class_eval`, and other metaprogramming are not
  resolved.
* Mixin (`include`/`extend`) edges are not yet emitted.

## License

MIT.
