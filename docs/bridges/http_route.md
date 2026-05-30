# HTTP route bridge (`scip-route`)

> The first cross-language Bridge. Language-neutral by construction:
> consumes a small metadata convention that any indexer can populate.
> No specific server framework or HTTP-client library is privileged.

## Status

| Item | Value |
|---|---|
| Bridge name | `http_route` |
| Version | 0.1.0 |
| Output scheme | `scip-route` |
| `requires` | (none) |
| Tests | 21 unit + 1 integration |

## Metadata convention

The Bridge does not parse source files. It reads structured metadata that
**indexers** attach to ``Symbol.extra``. This keeps the Bridge ignorant of
any specific framework's annotations, decorators, or routing DSL.

### Server side

A handler advertises itself with the ``http_route`` key:

```python
Symbol(
    id=...,
    extra={
        "http_route": {
            "method":       "GET",                # required, case-insensitive
            "path":         "/api/user/{id}",     # required, with optional {var}s
            "context_path": "/api/v1",            # optional, prepended to path
        }
    },
    ...,
)
```

The Bridge normalises ``method`` to upper-case and joins ``context_path``
with ``path`` to produce a single canonical ``full_path``. Repeated and
trailing slashes are collapsed.

### Client side

A caller advertises every HTTP call it issues:

```python
Symbol(
    id=...,
    extra={
        "http_calls": [
            {"method": "GET",  "url": "/api/v1/user/42", "confidence": "high"},
            {"method": "POST", "url": "/api/v1/user",    "confidence": "medium"},
        ]
    },
    ...,
)
```

``confidence`` follows the system-wide ladder (``high`` / ``medium`` /
``low``); unknown or missing values default to ``"medium"``.

## Outputs

For every unique ``(method, full_path)`` advertised by the server side,
the Bridge produces:

* A ``Route`` entry persisted to ``routes.json``.
* A synthetic intermediate ``SymbolID`` with the ``scip-route`` scheme,
  e.g. ``scip-route . . . api/GET#`/api/user/{id}`.``
* One ``Alias`` whose ``source`` is the intermediate and whose ``targets``
  are every server handler registered against the same route — multiple
  handlers per route are accepted and warned about (see ``ROUTE001``).
* ``routes_to`` edges from each server handler symbol to the intermediate.
* ``calls`` edges from each matched client symbol to the intermediate
  (carrying the client's ``confidence``).

## Path matching

A client ``url`` matches a server ``path`` when:

* both have the same number of ``/``-delimited segments after stripping
  query strings and fragments from the client URL;
* every static server segment is byte-identical to the client segment;
* ``{placeholder}`` server segments accept any single non-empty client
  segment.

If multiple server routes match, the first registered wins (deterministic
ordering by iteration over the underlying ``SymbolStore``).

## Diagnostics

| Code | Severity | When |
|---|---|---|
| `ROUTE001` | warning | Multiple distinct symbols register the same ``(method, full_path)``. Both are kept; the alias collects them. |
| `ROUTE002` | warning | A client call with ``confidence="high"`` has no matching server route in this index. Lower-confidence calls are silent (the URL was probably dynamic — see design §14). |

## Limitations

* The Bridge does **not** parse source files. If your indexer doesn't
  emit metadata, this Bridge contributes nothing.
* No regex / wildcard support in server paths. ``{name}`` placeholders
  are the only dynamic form supported.
* Path matching is exact-segment; no trailing-slash tolerance is added
  beyond the implicit stripping done before comparison.
* Cross-host matching is **not** attempted: ``url`` is treated as a
  path-only string. A client call to ``https://other-service/x`` would
  match a server route ``/x`` if both are otherwise compatible. Add a
  follow-up Bridge if your index covers multiple services.

## Example end-to-end (integration test)

See ``tests/integration/test_http_route_bridge_e2e.py`` for the canonical
example: four symbols are seeded into a ``JsonStore`` (two server, two
client, one with a path variable), the Bridge resolves them, the store
is committed, and the persisted ``routes.json`` / ``aliases.json`` /
``edges.json`` are asserted to have the shapes documented above.

## How an indexer ships this metadata

Any indexer for any framework / language can populate the keys:

| Framework family (illustrative) | What the indexer recognises |
|---|---|
| Decorator-based server framework | `@route("/x", method="GET")` or `@app.get("/x")` |
| Annotation-based server | `@GetMapping("/x")` style class + method annotations, possibly with class-level ``context_path`` |
| Router-table server | A registry-style file like `routes.py` listing `(method, path, handler)` tuples |
| HTTP-client library | `fetch("/api/...")`, `requests.get("...")`, custom wrappers — see design §14 for the layered-defence recognition strategy |

Indexers populate the convention; the Bridge stays language-neutral.
