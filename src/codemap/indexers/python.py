"""Python indexer — built on the stdlib ``ast`` module.

This is the first real-language indexer (Sprint N-1). It is shipped in the
main repository because (a) CodeMap is itself written in Python, so we get
dogfooding for free, and (b) ``ast`` is zero-dependency and trivially
correct. Per ADR-011, this is an *engineering* choice — Python carries no
product-level privilege over any other language that ships an indexer
through the ``codemap.indexers`` entry-point group (ADR-004).

Scheme: ``scip-python``. Symbol IDs encode the file path as a chain of
``namespace`` descriptors and the in-file scope as nested namespace / type
descriptors with the leaf descriptor matching the symbol kind:

* module-level function ``foo`` in ``src/m.py``:
  ``scip-python local . . src/m.py/foo().``
* class ``Bar`` in ``src/m.py``:
  ``scip-python local . . src/m.py/Bar#``
* method ``baz`` on ``Bar``:
  ``scip-python local . . src/m.py/Bar#baz().``
* module-level variable ``BAZ``:
  ``scip-python local . . src/m.py/BAZ.``

Resolution policy (MVP):

* Calls to bare names (``foo()``) resolve to the same-file symbol if one
  exists; otherwise they are dropped (no edge) and a low-confidence
  diagnostic is *not* emitted — bare-name resolution failures are common
  (built-ins, dynamic globals) and would flood diagnostics.
* Calls through ``self.x.y()`` are ignored at MVP — they require type
  inference. A diagnostic with code ``PY101`` is recorded at debug level.
* Class inheritance is recorded as ``extends`` edges; bases are kept as
  the raw textual name when the parent cannot be resolved.
* ``import`` / ``from ... import ...`` produce ``imports`` edges to a
  synthetic module symbol (kind=``module``).
"""

from __future__ import annotations

import ast
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-python"
LANG = "python"


class PythonIndexer:
    name: ClassVar[str] = "python"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.py", "*.pyi"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".py", ".pyi"}

    def index_file(
        self,
        path: Path,
        source: bytes,
        ctx: IndexContext,
    ) -> IndexResult:
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        file=ctx.relative_path,
                        code="PY002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        try:
            tree = ast.parse(text, filename=str(ctx.relative_path))
        except SyntaxError as exc:
            line = exc.lineno or 1
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        file=ctx.relative_path,
                        range=Range(start_line=line, end_line=line),
                        code="PY001",
                        message=f"syntax error: {exc.msg}",
                        producer=self.name,
                    )
                ]
            )
        visitor = _Visitor(ctx.relative_path)
        visitor.visit(tree)
        return IndexResult(
            symbols=visitor.symbols,
            edges=visitor.edges,
            diagnostics=visitor.diagnostics,
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


class _Visitor(ast.NodeVisitor):
    """Single-pass AST visitor that builds symbols, edges, and diagnostics."""

    def __init__(self, relative_path: PurePosixPath) -> None:
        self.relative_path = relative_path
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.diagnostics: list[Diagnostic] = []

        self._scope: list[_Scope] = []
        self._imports: dict[str, str] = {}
        """Local-name → dotted module path."""
        self._symbol_index: dict[str, SymbolID] = {}
        """Bare local name → SymbolID, used for same-file call resolution."""

    # ------------------------------------------------------------- modules

    def visit_Module(self, node: ast.Module) -> None:
        self.generic_visit(node)

    # ------------------------------------------------------------ imports

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self._imports[local] = alias.name
            target = _module_symbol_id(alias.name)
            source = self._enclosing_symbol_id()
            if source is not None:
                self.edges.append(
                    Edge(
                        source=source,
                        target=target,
                        kind="imports",
                        location=_node_range(node),
                    )
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            dotted = f"{module}.{alias.name}" if module else alias.name
            self._imports[local] = dotted
            target = _module_symbol_id(module or alias.name)
            source = self._enclosing_symbol_id()
            if source is not None:
                self.edges.append(
                    Edge(
                        source=source,
                        target=target,
                        kind="imports",
                        location=_node_range(node),
                    )
                )

    # -------------------------------------------------------- definitions

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        sid = self._make_id(node.name, _Kind.CLASS)
        sym = Symbol(
            id=sid,
            kind="class",
            language=LANG,
            file=self.relative_path,
            range=_node_range(node),
            doc=ast.get_docstring(node),
            extra={"decorators": _decorator_names(node.decorator_list)}
            if node.decorator_list
            else {},
        )
        self.symbols.append(sym)
        self._record_local_name(node.name, sid)

        for base in node.bases:
            base_name = _format_attr(base)
            if base_name is None:
                continue
            target = self._resolve_name(base_name)
            self.edges.append(
                Edge(
                    source=sid,
                    target=target,
                    kind="extends",
                    location=_node_range(base),
                    confidence="high"
                    if base_name in self._imports or base_name in self._symbol_index
                    else "medium",
                )
            )

        with self._push_scope(_Scope(name=node.name, kind=_Kind.CLASS)):
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node, is_async=True)

    def _visit_func(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        in_class = bool(self._scope) and self._scope[-1].kind is _Kind.CLASS
        kind: Literal["method", "function"] = "method" if in_class else "function"
        sid = self._make_id(node.name, _Kind.METHOD)
        extra: dict[str, object] = {}
        if is_async:
            extra["async"] = True
        if node.decorator_list:
            extra["decorators"] = _decorator_names(node.decorator_list)

        http_route = _extract_http_route(node.decorator_list)
        if http_route is not None:
            extra["http_route"] = http_route
        http_calls = _extract_http_calls(node.body)
        if http_calls:
            extra["http_calls"] = http_calls

        sym = Symbol(
            id=sid,
            kind=kind,
            language=LANG,
            file=self.relative_path,
            range=_node_range(node),
            signature=_function_signature(node),
            doc=ast.get_docstring(node),
            extra=extra,
        )
        self.symbols.append(sym)
        self._record_local_name(node.name, sid)

        with self._push_scope(_Scope(name=node.name, kind=_Kind.METHOD, symbol_id=sid)):
            for child in node.body:
                self.visit(child)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Only record module / class-level assignments. Function-locals are
        # not exposed as symbols.
        if not self._scope or self._scope[-1].kind is _Kind.CLASS:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    sid = self._make_id(target.id, _Kind.TERM)
                    sym_kind: Literal["field", "variable"] = "field" if self._scope else "variable"
                    sym = Symbol(
                        id=sid,
                        kind=sym_kind,
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(node),
                    )
                    self.symbols.append(sym)
                    self._record_local_name(target.id, sid)
        self.generic_visit(node)

    # -------------------------------------------------------------- calls

    def visit_Call(self, node: ast.Call) -> None:
        target_name = _format_attr(node.func)
        source = self._enclosing_callable_id()
        if source is not None and target_name is not None:
            target = self._resolve_name(target_name)
            self.edges.append(
                Edge(
                    source=source,
                    target=target,
                    kind="calls",
                    location=_node_range(node),
                    confidence=(
                        "high" if target_name.split(".")[0] in self._symbol_index else "medium"
                    ),
                )
            )
        self.generic_visit(node)

    # ----------------------------------------------------------- helpers

    def _enclosing_symbol_id(self) -> SymbolID | None:
        for scope in reversed(self._scope):
            if scope.symbol_id is not None:
                return scope.symbol_id
        return None

    def _enclosing_callable_id(self) -> SymbolID | None:
        for scope in reversed(self._scope):
            if scope.kind is _Kind.METHOD:
                return scope.symbol_id
        return None

    def _make_id(self, name: str, kind: _Kind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        for scope in self._scope:
            if scope.kind is _Kind.CLASS:
                descriptors.append(Descriptor(name=scope.name, kind=DescriptorKind.TYPE))
            elif scope.kind is _Kind.METHOD:
                # Functions/methods do not open a SymbolID namespace; their
                # body's nested definitions become siblings at the module
                # level. (Closures live as anonymous data — we don't index
                # them in this MVP.)
                pass
        if kind is _Kind.CLASS:
            descriptors.append(Descriptor(name=name, kind=DescriptorKind.TYPE))
        elif kind is _Kind.METHOD:
            descriptors.append(Descriptor(name=name, kind=DescriptorKind.METHOD))
        else:
            descriptors.append(Descriptor(name=name, kind=DescriptorKind.TERM))
        return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))

    def _record_local_name(self, name: str, sid: SymbolID) -> None:
        # Module-level and class-level names are addressable from the same
        # file; function-locals are not.
        if not self._scope or self._scope[-1].kind is _Kind.CLASS:
            self._symbol_index[name] = sid

    def _resolve_name(self, dotted: str) -> SymbolID:
        head, _, _ = dotted.partition(".")
        if dotted in self._symbol_index:
            return self._symbol_index[dotted]
        if head in self._symbol_index and "." not in dotted:
            return self._symbol_index[head]
        if head in self._imports:
            module = self._imports[head]
            # ``import x.y``: head=x, imports[x]=x.y, dotted may be x.func or x
            if "." in dotted:
                _, _, leaf = dotted.partition(".")
                return _external_symbol_id(module, leaf)
            return _module_symbol_id(module)
        # Bare unresolved name: return a `local`-scheme placeholder so the
        # edge survives but is clearly external. Bridges may later resolve it.
        return SymbolID(
            scheme="local",
            descriptors=(Descriptor(name=dotted, kind=DescriptorKind.TERM),),
        )

    def _push_scope(self, scope: _Scope) -> _ScopeContext:
        return _ScopeContext(self._scope, scope)


# ---------------------------------------------------------------------------
# Scope tracking
# ---------------------------------------------------------------------------


class _Kind(StrEnum):
    CLASS = "class"
    METHOD = "method"
    TERM = "term"


class _Scope:
    def __init__(self, *, name: str, kind: str, symbol_id: SymbolID | None = None) -> None:
        self.name = name
        self.kind = kind
        self.symbol_id = symbol_id


class _ScopeContext:
    def __init__(self, stack: list[_Scope], scope: _Scope) -> None:
        self._stack = stack
        self._scope = scope

    def __enter__(self) -> _Scope:
        self._stack.append(self._scope)
        return self._scope

    def __exit__(self, *exc: object) -> None:
        self._stack.pop()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _path_namespaces(path: PurePosixPath) -> list[Descriptor]:
    """Encode the file path as a chain of namespace descriptors.

    ``src/foo/bar.py`` becomes ``src/ foo/ bar.py/``. The trailing component
    keeps its ``.py`` extension to make symbols visually identifiable.
    """
    return [Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in path.parts]


def _module_symbol_id(dotted_module: str) -> SymbolID:
    """Synthetic SymbolID for a Python module (used as edge target)."""
    parts = dotted_module.split(".") if dotted_module else ["<root>"]
    descriptors = [Descriptor(name=p, kind=DescriptorKind.NAMESPACE) for p in parts[:-1]]
    descriptors.append(Descriptor(name=parts[-1], kind=DescriptorKind.META))
    return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))


def _external_symbol_id(dotted_module: str, leaf: str) -> SymbolID:
    """SymbolID for ``module.name`` references where the module is external."""
    parts = dotted_module.split(".") if dotted_module else []
    descriptors = [Descriptor(name=p, kind=DescriptorKind.NAMESPACE) for p in parts]
    descriptors.append(Descriptor(name=leaf, kind=DescriptorKind.TERM))
    return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))


def _node_range(node: ast.AST) -> Range:
    start_line = getattr(node, "lineno", 1) or 1
    end_line = getattr(node, "end_lineno", start_line) or start_line
    start_col = getattr(node, "col_offset", 0) or 0
    end_col = getattr(node, "end_col_offset", 0) or 0
    return Range(
        start_line=start_line,
        start_col=start_col,
        end_line=max(end_line, start_line),
        end_col=end_col,
    )


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args_src = ast.unparse(node.args)
    except Exception:  # pragma: no cover - defensive
        args_src = "..."
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args_src})"


def _decorator_names(decorators: list[ast.expr]) -> list[str]:
    out: list[str] = []
    for d in decorators:
        name = _format_attr(d.func if isinstance(d, ast.Call) else d)
        if name is not None:
            out.append(name)
    return out


def _format_attr(node: ast.AST) -> str | None:
    """Render an ``ast.Name`` / ``ast.Attribute`` chain back to dotted form."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _format_attr(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    return None


# ---------------------------------------------------------------------------
# HTTP route / call recognition (framework-agnostic, pattern-driven)
# ---------------------------------------------------------------------------

_HTTP_VERB_NAMES = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})
_HTTP_HIGH_CONF_CLIENTS = frozenset({"requests", "httpx", "aiohttp", "urllib3"})


def _extract_http_route(decorators: list[ast.expr]) -> dict[str, str] | None:
    """Return the ``http_route`` metadata if any decorator looks like a route.

    Two patterns are recognised, both framework-neutral:

    * ``@<obj>.{get,post,put,delete,patch,head,options}("/path")`` — the
      decorator's attribute name is the HTTP method.
    * ``@route("/path", methods=[...])`` or ``@<obj>.route("/path", method=...)``
      — the method defaults to ``GET`` when no kwarg is given.

    The path must be a literal string; dynamic paths (variables, concatenation)
    cannot be statically recovered and are ignored here — Bridges that need
    them must look in the source file.
    """
    for dec in decorators:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func

        # Pattern 1: <obj>.<verb>("path", ...)
        if isinstance(func, ast.Attribute):
            attr = func.attr.lower()
            if attr in _HTTP_VERB_NAMES:
                path = _first_str_arg(dec)
                if path is not None:
                    return {"method": attr.upper(), "path": path}

        # Pattern 2: route("path", method[s]=...) or <obj>.route("path", ...)
        verb_name: str | None = None
        if isinstance(func, ast.Name) and func.id == "route":
            verb_name = "route"
        elif isinstance(func, ast.Attribute) and func.attr in {"route", "add_url_rule"}:
            verb_name = func.attr
        if verb_name is not None:
            path = _first_str_arg(dec)
            if path is not None:
                method = _method_from_kwargs(dec) or "GET"
                return {"method": method, "path": path}
    return None


def _first_str_arg(call: ast.Call) -> str | None:
    """Return ``call.args[0]`` if it is a string literal, else ``None``."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _method_from_kwargs(call: ast.Call) -> str | None:
    """Pull the HTTP method out of ``method=...`` or ``methods=[...]`` kwargs."""
    for kw in call.keywords:
        if kw.arg not in {"method", "methods"}:
            continue
        value = kw.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value.upper()
        if isinstance(value, ast.List | ast.Tuple) and value.elts:
            first = value.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value.upper()
    return None


def _extract_http_calls(body: list[ast.stmt]) -> list[dict[str, str]]:
    """Walk ``body`` and collect ``<obj>.<verb>("url", ...)`` HTTP calls.

    The first positional argument must be a string literal that *looks* like a
    URL — leading ``/`` or ``http(s)://``. Without that guard, harmless calls
    like ``dict.get("key")`` would flood the index.

    Confidence is ``high`` when the receiver is a well-known HTTP client
    library (``requests`` / ``httpx`` / ``aiohttp`` / ``urllib3``), ``medium``
    otherwise — for those, the receiver name didn't prove the caller meant a
    network request.
    """
    out: list[dict[str, str]] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            verb = func.attr.lower()
            if verb not in _HTTP_VERB_NAMES:
                continue
            url = _first_str_arg(node)
            if url is None or not _looks_like_url(url):
                continue
            receiver_head = _attr_head(func.value)
            confidence = "high" if receiver_head in _HTTP_HIGH_CONF_CLIENTS else "medium"
            out.append(
                {
                    "method": verb.upper(),
                    "url": url,
                    "confidence": confidence,
                }
            )
    return out


def _looks_like_url(s: str) -> bool:
    return s.startswith("/") or s.startswith(("http://", "https://"))


def _attr_head(node: ast.AST) -> str | None:
    """Return the leftmost ``ast.Name.id`` in an attribute chain."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


__all__ = ["LANG", "SCHEME", "PythonIndexer"]
