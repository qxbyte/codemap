# codemap-jsp

> A JavaServer Pages (`.jsp`) indexer for
> [CodeMap](https://github.com/qxbyte/codemap), distributed as an
> independent PyPI package. Targets legacy Java web projects that
> still ship `.jsp` views.

## What it captures

JSP files are HTML containers with embedded Java. The indexer scans
five top-level constructs:

| JSP construct | Captured as |
|---|---|
| `<%@ page import="..." %>` | `extra.jsp_imports` on the page symbol |
| `<%@ include file="..." %>` | `extra.jsp_includes` on the page symbol |
| `<%! ... %>` (declaration block) | Java members parsed by `tree-sitter-java`; methods → `method`, fields → `variable`, nested classes → `class` |
| `<% ... %>` (scriptlet) | **Skipped** — scriptlet locals are per-request state, not a stable interface |
| `<form action="..." method="..."/>` and `<a href="...">` | `extra.http_client_calls` on the page symbol — consumed by the host's `http_route` bridge to link the page to its server controller |

Every JSP file produces **one page-level pseudo-class symbol** plus
zero or more member symbols from any `<%! ... %>` blocks. The page
name is derived from the file basename (`UserList.jsp` → `UserList`).

## Why this matters for AI agents on legacy projects

A typical Spring MVC + JSP project has:

```
src/main/java/com/example/UserController.java
  @PostMapping("/api/users") void create(User u) { ... }

src/main/webapp/WEB-INF/views/users.jsp
  <form action="/api/users" method="POST"> ... </form>
```

The `http_route` bridge ships in `codemap-core`. Once both files are
indexed, the bridge sees:

* the server route `(POST, /api/users)` exposed by `UserController.create`
* the client call `(POST, /api/users)` advertised by `users.jsp`

…and adds a `calls` edge from the page to the controller. AI agents
can now answer "what JSP pages submit to this controller?" with a
single `codemap callers` query — no grepping HTML for URLs.

## Install

```bash
pip install codemap-jsp
```

`tree-sitter-java` is a hard dependency (used to parse declaration
blocks). No tree-sitter-jsp grammar is needed.

## SymbolID encoding

```
scip-jsp . . . src/main/webapp/views/UserList.jsp/UserList#tag().
└──────┘     └──────────────────────────────────────────────────┘
  scheme         path / page pseudo-class / member
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Limits / next steps

* Scriptlet (`<% ... %>`) bodies are not indexed for symbol extraction
  — they would surface per-request locals as noise. A future v0.2.x
  could optionally extract control-flow shape from scriptlets to
  support cross-page navigation.
* JSTL tags (`<c:if>`, `<c:forEach>`) and EL expressions (`${...}`)
  are not parsed. A `codemap-jstl` companion plugin could surface
  declared `<c:set var="..."/>` variables if there's demand.
* Tag files (`.tag` / `.tagx`) are supported on the same code path as
  pages but their unique `<%@ attribute name="..." %>` directives are
  not yet surfaced as individual symbols.

## License

MIT — same as the host project.
