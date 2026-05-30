# codemap-csharp

> A C# language indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-c-sharp`:

| AST node | Symbol kind |
|---|---|
| `namespace_declaration` (incl. `qualified_name`) | namespace prefix (recursed into) |
| `class_declaration` | `class` |
| `interface_declaration` | `class` (`extra.csharp_kind=interface`) |
| `struct_declaration` | `class` (`extra.csharp_kind=struct`) |
| `record_declaration` | `class` (`extra.csharp_kind=record`) |
| `enum_declaration` | `class` (`extra.csharp_kind=enum`) |
| `delegate_declaration` | `class` (`extra.csharp_kind=delegate`) |
| `method_declaration` | `method` |
| `property_declaration` | `field` (`extra.csharp_kind=property`) |
| `field_declaration` → `variable_declarator` | `field` |
| `enum_member_declaration` | `field` |

Top-level statements (C# 9+) are not surfaced as named symbols.

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-csharp"
```

## File patterns

* `*.cs`, `*.csx`

## Limits

* File-scoped namespaces (``namespace App;``) and block-scoped namespaces
  are both handled, but global usings are not emitted as symbols.
* Partial classes are emitted as separate symbols per file — the index
  layer does not currently merge them.

## License

MIT.
