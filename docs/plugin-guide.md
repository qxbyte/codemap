# Writing a CodeMap plugin

> CodeMap's indexers and bridges are **plugin-first by design** (ADR-004).
> Internal indexers and third-party packages register through the **same
> entry-point groups** and the same Protocols — there is no "first-class"
> path reserved for the main repository.

This guide walks through the steps to ship a new language indexer (or a
new bridge) as an **independent PyPI package**. The reference
implementation is the
[`codemap-typescript`](../plugins/codemap-typescript) plugin that lives
in this repository under `plugins/`.

## 1 · Package layout

A plugin is a normal Python package with one entry-point declaration in
`pyproject.toml`. The minimum useful shape is:

```
codemap-yourlang/
├── pyproject.toml           # entry_points + dependency on `codemap`
├── README.md
└── src/codemap_yourlang/
    ├── __init__.py          # exports the indexer class
    └── indexer.py           # implements the protocol
```

Tests under `tests/` go through the same `codemap.core` and
`codemap.indexers.base` imports the host CLI uses — there is no extra
test harness to learn.

## 2 · The Protocol

Implement
[`codemap.indexers.base.Indexer`](../src/codemap/indexers/base.py):

```python
class Indexer(Protocol):
    name: ClassVar[str]            # unique short id ('typescript', 'go', ...)
    version: ClassVar[str]         # plugin version, independent of CodeMap
    file_patterns: ClassVar[list[str]]  # ['*.ts', '*.tsx']
    languages: ClassVar[list[str]]      # ['typescript']

    def supports(self, path: Path) -> bool: ...
    def index_file(
        self,
        path: Path,
        source: bytes,
        ctx: IndexContext,
    ) -> IndexResult: ...
```

`IndexResult` is a Pydantic model exposing `symbols`, `edges`, `routes`,
`diagnostics`. SymbolIDs use the SCIP grammar (ADR-001) — see
[`codemap.core.symbol`](../src/codemap/core/symbol.py) for the parser
and helpers.

## 3 · Pick a SCIP scheme

Use `scip-<lang>` for the obvious one-language case. Reserve a fresh
scheme name for any non-source asset (`scip-openapi`, `scip-prisma`,
…) so other plugins can grow alongside without collision.

```python
SCHEME = "scip-yourlang"
```

## 4 · Encode the file path

The convention every existing indexer follows: the file path is a chain
of `namespace` descriptors. The trailing component keeps its extension,
making symbols visually identifiable at the CLI:

```
scip-yourlang . . . src/foo/Bar.yl/Klass#method().
└───────────────┘ └──────────────────┘ └───┘ └─────┘
     scheme         path namespaces    type  method
```

## 5 · Register through entry_points

```toml
[project.entry-points."codemap.indexers"]
yourlang = "codemap_yourlang:YourLangIndexer"
```

That single line is the *only* coupling between your package and the
host. The plugin is now discoverable by `codemap doctor`:

```
$ pip install codemap-yourlang
$ codemap doctor
Registered indexers
┃ name        ┃ version ┃ languages ┃ file_patterns ┃
┃ yourlang    ┃ 0.1.0   ┃ yourlang  ┃ *.yl          ┃
…
```

## 6 · Optional: ship a Bridge too

Bridges register under the parallel `codemap.bridges` group and
implement
[`codemap.core.bridge.base.Bridge`](../src/codemap/core/bridge/base.py).
Typical bridges:

* HTTP-route resolver (pattern: `codemap-yourlang-http`)
* Cross-module call resolver (pattern: `codemap-yourlang-cross-module`)
* Container / DI wiring resolver
* IDL / Schema cross-validators (protobuf, OpenAPI, GraphQL, …)

A bridge runs *after* every indexer and operates on the
`ReadOnlyStore` view, so it can be language-neutral if its inputs are
metadata the indexer attached to `Symbol.extra`.

## 7 · Tests

`pytest`. The `codemap.core` / `codemap.indexers.base` imports work
directly, so unit tests look like the ones in
[`tests/unit/test_python_indexer.py`](../tests/unit/test_python_indexer.py)
or the [`codemap-typescript` plugin tests](../plugins/codemap-typescript/tests).

## 8 · User experience

* `codemap.indexers.disabled: ["yourlang"]` in `.codemap/config.yaml`
  disables the plugin without uninstalling.
* `codemap doctor` and `codemap config show` both reflect plugin state
  immediately — no main-repo change ever needed.
* `codemap index --dry-run` reports per-indexer file counts so the
  plugin's contribution is visible.

## 9 · Versioning

Follow SemVer on the plugin and pin a minimum `codemap` version in
`dependencies`. The Indexer / Bridge Protocols evolve under the design
doc's ADR-006 schema-version policy; a minor CodeMap bump never
breaks a plugin that satisfied the previous protocol.

## Reference plugin

[`plugins/codemap-typescript/`](../plugins/codemap-typescript) is a
fully working example:

* `tree-sitter-typescript` for parsing.
* `*.ts` + `*.tsx` file patterns.
* Functions / classes / interfaces / module-level variables.
* `pip install -e plugins/codemap-typescript/` makes `codemap doctor`
  list it next to the built-in indexers.
* 14 unit tests, kept inside the plugin package so the host repo's CI
  doesn't have to know about them.

That's the entire footprint. No magic, no main-repo PR, no privileged
"core" status — your plugin and the built-in Python indexer use the
same door.
