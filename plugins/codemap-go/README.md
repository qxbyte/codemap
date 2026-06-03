# codemap-go

> A Go indexer for [CodeMap](https://github.com/qxbyte/codemap), shipped
> as an independent PyPI package.

## What it captures

Backed by `tree-sitter-go`:

| AST node | Symbol kind |
|---|---|
| `function_declaration` | `function` |
| `method_declaration` | `method` (attached to its receiver type) |
| `type_declaration` containing `struct_type` | `class` (with `extra.go_kind=struct`) |
| `type_declaration` containing `interface_type` | `class` (with `extra.go_kind=interface`) |
| `type_declaration` (other) | `class` (with `extra.go_kind=type`) |
| `const_declaration` (top-level) | `variable` (with `extra.go_kind=const`) |
| `var_declaration` (top-level) | `variable` |

`package_clause` is captured as `extra.package` on every symbol-producing
type so a downstream bridge can use it for cross-file resolution.

Method receivers — both `func (u User) M()` and `func (u *User) M()` —
attach the method to its `User` type, producing
`scip-go . . . main.go/User#Login().`.

## SymbolID encoding

```
scip-go . . . pkg/user/user.go/User#Login().
└──────┘ └─────────────────────┘ └────┘ └─────┘
 scheme        file path          type   method
```

## Install

```bash
pip install codemap-go
```

After install, `codemap doctor` lists `go` alongside the other indexers
on identical terms (ADR-004 + ADR-L001).

## Limits

* No `imports` edges. Top-level imports are recorded for the package
  table but not turned into edges.
* No generic constraints / type-parameter descriptors.
* Method bodies are not traversed for call edges yet.
* Anonymous structs and function-typed fields are skipped.

## License

MIT.
