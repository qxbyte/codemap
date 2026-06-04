# codemap-javascript

> A JavaScript / JSX indexer for [CodeMap](https://github.com/qxbyte/codemap),
> distributed as an independent PyPI package.

## What this package covers

| Extension | Grammar | Notes |
|---|---|---|
| `.js` | `tree-sitter-javascript` | Plain JavaScript |
| `.jsx` | `tree-sitter-javascript` | React-style JSX (the grammar handles JSX natively) |
| `.mjs` | `tree-sitter-javascript` | ES module |
| `.cjs` | `tree-sitter-javascript` | CommonJS module |

A single grammar instance handles all four extensions — `.jsx` is **not**
a separate grammar in tree-sitter-javascript.

## Install

```bash
pip install codemap-javascript
```

After installation, `codemap doctor` lists `javascript` alongside the
built-in indexers (ADR-004 + ADR-L001).

## What it captures

Backed by `tree-sitter-javascript`. Single-file, no cross-file resolution:

| AST node | Symbol kind | SymbolID descriptor |
|---|---|---|
| `function_declaration` | `function` | `<path>/name().` |
| `class_declaration` | `class` | `<path>/Cls#` |
| `method_definition` (inside class) | `method` | `<path>/Cls#name().` |
| Top-level `const` / `let` / `var` | `variable` | `<path>/Name.` |

Edges:

* `import_statement` is read for future cross-module bridge consumption,
  but no edge is emitted at the module top-level (parity with the
  TypeScript plugin).

## SymbolID encoding

```
scip-javascript . . . src/app/Service.js/UserService#login().
└─────────────┘     └──────────────────────────────────────┘
     scheme              file → namespaces / type / method
```

## Why a separate plugin (vs. extending `codemap-typescript`)

TypeScript is a syntactic superset of JavaScript, so `tree-sitter-typescript`
*can* parse most `.js` / `.jsx` files. We ship a dedicated plugin instead
for three reasons:

1. **Clean dependency**: `codemap-javascript` does not depend on
   `tree-sitter-typescript`. Users who only have JavaScript code do not
   need the larger grammar.
2. **JS-specific error recovery**: when a `.js` file has a syntax error,
   the JavaScript grammar's error nodes point at JS-shaped tokens rather
   than TS-shaped ones, which produces tighter diagnostics.
3. **Independent versioning**: JS language updates (decorators, class
   fields, RegExp `v` flag) can ship at their own cadence without
   bumping the TypeScript plugin.

For pure type-extraction purposes the two plugins produce equivalent
symbol output for `.js` / `.jsx` files. Install whichever matches your
codebase; install both if you have a mixed code-base.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Limits / next steps

* No cross-file `import` resolution. A `javascript_cross_module` bridge,
  sibling to `python_cross_module`, would be a future addition.
* Arrow functions assigned to top-level `const` are indexed as
  `variable`, not `function` — matching the TypeScript plugin. Named
  arrow detection across both plugins is a v0.2.x improvement.
* JSX-specific component patterns are not yet captured beyond the
  underlying function/class symbols.

## License

MIT — same as the host project.
