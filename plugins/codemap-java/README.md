# codemap-java

> A Java indexer for [CodeMap](https://github.com/qxbyte/codemap),
> distributed as an independent PyPI package.

## What it captures

Backed by `tree-sitter-java`. Single-file, no cross-file type inference (MVP):

| AST node | Symbol kind |
|---|---|
| `class_declaration` | `class` |
| `interface_declaration` | `interface` (stored as `class` with `extra.java_kind=interface`) |
| `enum_declaration` | stored as `class` with `extra.java_kind=enum` |
| `record_declaration` | stored as `class` with `extra.java_kind=record` |
| `method_declaration` (inside type) | `method` |
| `constructor_declaration` | `method` (signature prefixed with `<init>`) |
| `field_declaration` (inside type) | `field` |

Package declarations are captured and used as a prefix for the in-file
`package` namespace.

## SymbolID encoding

```
scip-java . . . src/com/example/Greeter.java/Greeter#hello().
└────────┘ └────────────────────────────────┘ └──────┘ └─────┘
  scheme              file path                  type   method
```

## Install

```bash
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
```

After installation, `codemap doctor` lists `java` next to the other
indexers on identical terms — same Indexer Protocol, same entry-point
group, no main-repo change required (ADR-004 + ADR-L001).

## Limits

* No `extends` / `implements` edges yet. Easy to add in v0.2.0.
* No generic-parameter descriptors.
* No annotation extraction (planned).
* Anonymous classes are skipped.

## License

MIT.
