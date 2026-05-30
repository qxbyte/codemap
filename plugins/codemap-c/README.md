# codemap-c

> A C language indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-c`:

| AST node | Symbol kind |
|---|---|
| `function_definition` | `function` |
| `struct_specifier` (named, with body) | `class` (`extra.c_kind=struct`) |
| `union_specifier` (named, with body) | `class` (`extra.c_kind=union`) |
| `enum_specifier` (named) | `class` (`extra.c_kind=enum`) |
| `type_definition` (`typedef`) | `class` (`extra.c_kind=typedef`) |
| `preproc_def` (`#define X ...`) | `variable` (`extra.c_kind=macro`) |
| Top-level `declaration` with initializer | `variable` |
| `field_declaration` inside a struct/union body | `field` (attached to the parent) |

Function bodies are not walked for inner declarations — locals are not
script-level interface.

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-c"
```

## File patterns

* `*.c`, `*.h`

## Limits

* Preprocessor conditionals (`#ifdef`/`#if`) parse but no branch selection
  is performed — both arms contribute symbols.
* Function declarations (prototypes) are not emitted; only definitions.
* Forward struct declarations without a body are skipped.

## License

MIT.
