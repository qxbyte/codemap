# Python indexer (`scip-python`)

> Built on the stdlib `ast` module. Zero non-Python dependencies. Sprint
> N-1's first-language pick, per ADR-011 — an engineering convenience
> (CodeMap is written in Python; we get dogfooding for free), **not** a
> product preference (ADR-L001).

## Status

| Item | Value |
|---|---|
| Indexer name | `python` |
| Version | 0.1.0 |
| Scheme | `scip-python` |
| File patterns | `*.py`, `*.pyi` |
| Tests | 25 unit + 3 golden fixtures (all passing) |
| Dogfood baseline | 48 files / 437 symbols / 1232 edges / 0 diagnostics on the CodeMap repository itself |

## What it captures

| AST node | Symbol kind | SymbolID descriptor |
|---|---|---|
| Module-level `def` | `function` | `<path>/name().` |
| `def` inside class | `method` | `<path>/Cls#name().` |
| `async def` | same as above + `extra.async = True` | |
| `class` (module-level or nested) | `class` | `<path>/Cls#` |
| Module-level `Name = ...` | `variable` | `<path>/Name.` |
| Class-level `Name = ...` | `field` | `<path>/Cls#Name.` |

| AST node | Edge kind | Notes |
|---|---|---|
| `ast.Call` inside a function/method | `calls` | Resolution: same-file ✓ (high), imported name ✓ (medium), bare unknown → `local`-scheme placeholder edge |
| `import x` / `from x import y` (inside a callable) | `imports` | At module level the import has no enclosing callable, so no edge is emitted — only the local name table is updated |
| `class X(Base)` | `extends` | High confidence if `Base` is in the local symbol table or the import table; medium otherwise |

Decorators are captured as `symbol.extra["decorators"] = ["staticmethod", ...]`.
The `signature` field stores a readable `def name(args)` reconstruction.

## SymbolID encoding

The file path is encoded as a chain of `namespace` descriptors:

```
scip-python . . . src/auth/login.py/LoginHandler#verify().
└─────┬─────┘ └────────┬──────────┘ └──┬──┘  └───┬───┘
   scheme       path namespaces       type   method
```

The trailing component keeps its `.py` extension to make symbols visually
identifiable. Manager / package / version default to `.` placeholders for
non-installed code; if you pin a real distribution coordinate (`pip
metadata` available) you can populate them in a future revision — the
parser already accepts both forms.

## Limitations

These are the **known gaps** in v0.1.0 — none are silent. Symbols that the
indexer cannot resolve produce either a low/medium-confidence edge or a
`local`-scheme placeholder so a Bridge or query layer can address them
explicitly.

* **Dynamic typing**: `self.x.method()` and `obj.method()` calls where
  `obj`'s type cannot be inferred from imports are recorded as edges
  whose target uses the `local` scheme — they're not lost, but they're
  not resolved either. A type-inference bridge could refine them later.
* **`exec` / `globals()[...]` / `getattr` runtime lookups**: simply not
  modeled. These are uncommon in well-typed codebases and out of scope
  for a static indexer.
* **Closure-captured names**: closures themselves are not indexed as
  symbols. Their bodies are walked for outer-scope calls, but the
  closure itself does not appear in `symbols.json`.
* **Conditional imports**: `if TYPE_CHECKING: import x` is treated the
  same as any other import — the local name binds, and downstream
  call edges resolve through it. This is intentional; the TYPE_CHECKING
  flag is a runtime concern, not a static one.
* **Relative imports across packages**: `from .sibling import x` resolves
  through the local name table, so calls to `x()` are tagged correctly.
  Cross-package relative resolution (`from ..parent.module import x`)
  works for the local-name side; the imported module's SymbolID may not
  match a sibling file's path encoding if you index both — to be
  improved when an integration bridge lands.

## Confidence ladder

| Resolution path | `confidence` on the resulting edge |
|---|---|
| Same-file callable name found in local symbol table | `high` |
| Bare name found in import table (`from x import y`) | `medium` |
| Attribute access through imported alias (`p.foo` where `p = path`) | `medium` |
| Bare name not in either table → `local`-scheme placeholder edge | `medium` |
| `extends Base` where `Base` is local or imported | `high` |
| `extends Base` where `Base` is neither | `medium` |

## Performance baseline (informational; ADR-010 will lock in regression gates)

Measured against the CodeMap repository itself (48 files, ~5 000 LoC):

| Metric | Value |
|---|---|
| Index time | < 1 s on Apple M-series single core |
| Symbols / file (mean) | 9.1 |
| Edges / file (mean) | 25.7 |
| Diagnostics | 0 |
| `.codemap/` size | ~ 1.5 MB |

## Tests

* `tests/unit/test_python_indexer.py` — 25 inline-source unit cases
* `tests/fixtures/indexers/python/` — 3 golden directory fixtures
  (basics, inheritance, imports). Each fixture has `input/*.py` plus
  `expected/symbol_ids.txt` with one sorted symbol ID per line.

The Sprint-N model wants ≥ 20 golden fixtures per language. This Sprint
ships 3; further fixtures will land alongside the next language Indexer
(which will benefit from the runner mechanics already in place).
