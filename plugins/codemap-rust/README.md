# codemap-rust

> A Rust indexer for [CodeMap](https://github.com/qxbyte/codemap), shipped
> as an independent PyPI package.

## What it captures

Backed by `tree-sitter-rust`:

| AST node | Symbol kind |
|---|---|
| `function_item` (free) | `function` |
| `function_item` (inside `impl`) | `method` (attached to the impl'd type) |
| `function_signature_item` (inside `trait`) | `method` (attached to the trait) |
| `struct_item` | `class` (with `extra.rust_kind=struct`) |
| `enum_item` | `class` (with `extra.rust_kind=enum`) |
| `trait_item` | `class` (with `extra.rust_kind=trait`) |
| `const_item` | `variable` (with `extra.rust_kind=const`) |
| `static_item` | `variable` (with `extra.rust_kind=static`) |

`impl Trait for Type` blocks attach methods to `Type` (the receiver), so
both inherent and trait impls end up addressable under the same
`Type#method()` shape.

## SymbolID encoding

```
scip-rust . . . src/user.rs/User#login().
```

## Install

```bash
pip install codemap-rust
```

After install, `codemap doctor` lists `rust` alongside the other
indexers on identical terms (ADR-004 + ADR-L001).

## Limits

* Methods on generic types (`impl<T> Foo<T>`) attach to `Foo` without
  the generic parameter — adequate for code search, lossy for type
  checking.
* Macros are not expanded; their declarations are not captured as
  symbols.
* `mod` declarations are not turned into namespace prefixes; the file
  path is the only namespace.

## License

MIT.
