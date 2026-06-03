# codemap-scala

> A Scala language indexer for [CodeMap](https://github.com/qxbyte/codemap),
> shipped as an independent PyPI package.

## What it captures

Backed by `tree-sitter-scala`:

| AST node | Symbol kind |
|---|---|
| `package_clause` (incl. `package_identifier`) | namespace prefix |
| `class_definition` (incl. `case class`) | `class` (`extra.scala_kind=class` / `case_class`) |
| `object_definition` (incl. `case object`) | `class` (`extra.scala_kind=object`) |
| `trait_definition` | `class` (`extra.scala_kind=trait`) |
| `type_definition` (top-level alias) | `class` (`extra.scala_kind=type`) |
| `function_definition` / `function_declaration` | `method` |
| `val_definition` (top-level or in template body) | `field` (`extra.scala_kind=val`) |
| `var_definition` (top-level or in template body) | `field` (`extra.scala_kind=var`) |
| `class_parameter` (in `case class`) | `field` (`extra.scala_kind=case_field`) |

## Install

```bash
pip install codemap-scala
```

## File patterns

* `*.scala`, `*.sc`

## Limits

* Implicits and Scala 3 `given` declarations parse but are not specifically
  tagged.
* Anonymous classes (`new T { ... }`) are not surfaced.
* Block-scoped `def` inside a method body is not emitted — it is private
  to that method.

## License

MIT.
