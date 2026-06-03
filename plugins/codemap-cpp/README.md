# codemap-cpp

> A C++ language indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-cpp`:

| AST node | Symbol kind |
|---|---|
| `namespace_definition` | namespace prefix (recursed into) |
| `class_specifier` (named, with body) | `class` (`extra.cpp_kind=class`) |
| `struct_specifier` (named, with body) | `class` (`extra.cpp_kind=struct`) |
| `union_specifier` (named, with body) | `class` (`extra.cpp_kind=union`) |
| `enum_specifier` | `class` (`extra.cpp_kind=enum`) |
| `function_definition` (top-level or in namespace) | `function` |
| `function_definition` (inside class body) | `method` |
| `field_declaration` (data member) | `field` |
| `template_declaration` wrapping any of the above | unwraps to the inner declaration |

## Install

```bash
pip install codemap-cpp
```

## File patterns

* `*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx`

## Limits

* Out-of-class method definitions (``void Foo::bar() { ... }``) appear as
  free functions, not as members of ``Foo``.
* `using` declarations and aliases are not emitted as symbols.
* Macro-only ``#define`` constants are not captured (see ``codemap-c``).

## License

MIT.
