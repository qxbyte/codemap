"""HTTP route bridge — language-neutral client ↔ server linker.

The bridge knows nothing about specific server frameworks or HTTP client
libraries. Instead, it relies on a small **metadata convention** that any
indexer can populate. Whether the source language is Python, TypeScript,
Go, Rust, or anything else does not matter; the contract is the same.

## Metadata convention

A server-side handler advertises itself by setting two keys on its
``Symbol.extra`` dict::

    "http_route": {
        "method": "GET",                # required, case-insensitive
        "path":   "/api/user/{id}",     # required, with optional {var}s
        "context_path": "/api/v1",      # optional, prepended to ``path``
    }

A client-side caller advertises every HTTP call it issues::

    "http_calls": [
        {
            "method":     "GET",
            "url":        "/api/v1/user/42",
            "confidence": "high",       # optional; defaults to "medium"
        },
        ...
    ]

## Resolution output

For each unique ``(method, full_path)`` advertised by the server side, the
bridge mints a synthetic intermediate symbol with the ``scip-route`` scheme
(e.g. ``scip-route . . . api/GET#`/api/user/{id}`.``). Server handlers and
client calls both relate to this intermediate via :class:`Alias` and
:class:`Edge` entries — that way the symbol-store doesn't have to carry
a direct ``client → server`` edge for every (method, path) combination.

The bridge produces three kinds of outputs:

* :class:`Route` entries (one per server-advertised route) for
  ``routes.json``.
* :class:`Alias` entries linking the intermediate to its server handlers
  (and, when an exact client URL matches, the client callers).
* :class:`Edge` entries with ``kind="routes_to"`` (``server_handler →
  route_intermediate``) and ``kind="calls"`` (``client_caller →
  route_intermediate``) so the existing call-graph queries keep working.

## Path matching

A client ``url`` matches a server ``path`` if they have the same number of
``/``-separated segments and every static server segment equals the
corresponding client segment; ``{placeholder}`` segments in the server
path match any non-empty client segment. Trailing slashes and query
strings are ignored on the client side.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import ClassVar

from codemap.core.models import (
    Alias,
    BridgeResult,
    Confidence,
    Diagnostic,
    Edge,
    Route,
)
from codemap.core.store import ReadOnlyStore
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID

SCHEME = "scip-route"


class HttpRouteBridge:
    name: ClassVar[str] = "http_route"
    version: ClassVar[str] = "0.1.0"
    requires: ClassVar[list[str]] = []

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        server_routes: list[_ServerRoute] = []
        client_calls: list[_ClientCall] = []

        for sym in store.iter_symbols():
            extra = sym.extra
            server_meta = _read_server_route(extra)
            if server_meta is not None:
                method, path, context = server_meta
                full_path = _join_path(context, path)
                server_routes.append(
                    _ServerRoute(
                        method=method,
                        full_path=full_path,
                        symbol_id=sym.id,
                        file=sym.file,
                    )
                )
            for call in _read_client_calls(extra):
                client_method, url, conf = call
                client_calls.append(
                    _ClientCall(
                        method=client_method,
                        url=url,
                        symbol_id=sym.id,
                        confidence=conf,
                        file=sym.file,
                    )
                )

        # Mint one intermediate symbol per unique (method, full_path)
        intermediates: dict[tuple[str, str], SymbolID] = {}
        for route in server_routes:
            key = (route.method, route.full_path)
            if key not in intermediates:
                intermediates[key] = _route_symbol_id(route.method, route.full_path)

        routes: list[Route] = []
        aliases: list[Alias] = []
        edges: list[Edge] = []
        diagnostics: list[Diagnostic] = []

        # Group server handlers per route so we can warn on duplicates.
        handlers: defaultdict[tuple[str, str], list[_ServerRoute]] = defaultdict(list)
        for route in server_routes:
            handlers[(route.method, route.full_path)].append(route)

        for (method, full_path), group in handlers.items():
            route_sid = intermediates[(method, full_path)]
            routes.append(
                Route(
                    method=method,
                    path=full_path,
                    symbol_id=route_sid,
                    context_path=None,
                )
            )
            aliases.append(
                Alias(
                    source=route_sid,
                    targets=[handler.symbol_id for handler in group],
                    producer=self.name,
                    confidence="high",
                )
            )
            edges.extend(
                Edge(
                    source=handler.symbol_id,
                    target=route_sid,
                    kind="routes_to",
                    confidence="high",
                )
                for handler in group
            )
            if len(group) > 1:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        file=group[0].file,
                        code="ROUTE001",
                        message=(
                            f"multiple handlers registered for {method} {full_path}: "
                            f"{len(group)} symbols"
                        ),
                        producer=self.name,
                    )
                )

        # Match each client call against the known server routes.
        server_keys = list(intermediates.keys())
        for cc in client_calls:
            matched = _match_route(cc.method, cc.url, server_keys)
            if matched is None:
                if cc.confidence == "high":
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            file=cc.file,
                            code="ROUTE002",
                            message=(
                                f"client {cc.method} {cc.url} has no matching "
                                f"server route in this index"
                            ),
                            producer=self.name,
                        )
                    )
                continue
            route_sid = intermediates[matched]
            edges.append(
                Edge(
                    source=cc.symbol_id,
                    target=route_sid,
                    kind="calls",
                    confidence=cc.confidence,
                )
            )

        return BridgeResult(
            edges=edges,
            aliases=aliases,
            routes=routes,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# Metadata adapters
# ---------------------------------------------------------------------------


class _ServerRoute:
    __slots__ = ("file", "full_path", "method", "symbol_id")

    def __init__(
        self,
        *,
        method: str,
        full_path: str,
        symbol_id: SymbolID,
        file: PurePosixPath,
    ) -> None:
        self.method = method
        self.full_path = full_path
        self.symbol_id = symbol_id
        self.file = file


class _ClientCall:
    __slots__ = ("confidence", "file", "method", "symbol_id", "url")

    def __init__(
        self,
        *,
        method: str,
        url: str,
        symbol_id: SymbolID,
        confidence: Confidence,
        file: PurePosixPath,
    ) -> None:
        self.method = method
        self.url = url
        self.symbol_id = symbol_id
        self.confidence: Confidence = confidence
        self.file = file


def _read_server_route(extra: dict[str, object]) -> tuple[str, str, str] | None:
    raw = extra.get("http_route")
    if not isinstance(raw, dict):
        return None
    method_raw = raw.get("method")
    path_raw = raw.get("path")
    if not isinstance(method_raw, str) or not isinstance(path_raw, str):
        return None
    method = method_raw.strip().upper()
    path = path_raw.strip()
    if not method or not path:
        return None
    ctx_raw = raw.get("context_path")
    context = ctx_raw.strip() if isinstance(ctx_raw, str) else ""
    return method, path, context


_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


def _read_client_calls(
    extra: dict[str, object],
) -> Iterable[tuple[str, str, Confidence]]:
    raw = extra.get("http_calls")
    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, dict):
            continue
        method_raw = item.get("method")
        url_raw = item.get("url")
        if not isinstance(method_raw, str) or not isinstance(url_raw, str):
            continue
        method = method_raw.strip().upper()
        url = url_raw.strip()
        if not method or not url:
            continue
        conf_raw = item.get("confidence")
        if isinstance(conf_raw, str) and conf_raw in _VALID_CONFIDENCE:
            confidence: Confidence = conf_raw  # type: ignore[assignment]
        else:
            confidence = "medium"
        yield method, url, confidence


# ---------------------------------------------------------------------------
# Path manipulation
# ---------------------------------------------------------------------------


def _join_path(context: str, path: str) -> str:
    """Concatenate ``context_path`` (optional) with ``path``.

    Both arguments may or may not include leading / trailing slashes; the
    result is normalised to a single leading ``/`` and no trailing ``/``
    unless the entire result is ``/``.
    """
    parts: list[str] = []
    for piece in (context, path):
        stripped = piece.strip()
        if not stripped:
            continue
        parts.extend(seg for seg in stripped.split("/") if seg)
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def _match_route(
    method: str,
    url: str,
    server_routes: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """Return the first ``(method, path)`` from ``server_routes`` that matches.

    Path-variable segments (``{name}``) on the server side match any
    single non-empty client segment. Query strings on the client URL are
    stripped before comparison. Trailing slashes are normalised.
    """
    client_path = url.split("?", 1)[0].split("#", 1)[0]
    c_segments = [s for s in client_path.split("/") if s]
    for s_method, s_path in server_routes:
        if s_method != method:
            continue
        s_segments = [s for s in s_path.split("/") if s]
        if len(s_segments) != len(c_segments):
            continue
        ok = True
        for s, c in zip(s_segments, c_segments, strict=True):
            if s.startswith("{") and s.endswith("}") and len(s) >= 2:
                if not c:
                    ok = False
                    break
                continue
            if s != c:
                ok = False
                break
        if ok:
            return (s_method, s_path)
    return None


# ---------------------------------------------------------------------------
# Intermediate symbol minting
# ---------------------------------------------------------------------------


def _route_symbol_id(method: str, path: str) -> SymbolID:
    """Build the ``scip-route`` intermediate symbol.

    Shape: ``scip-route . . . api/<METHOD>#`<path>`.``. The path is held
    in a TERM descriptor so it can contain slashes; the parser auto-
    escapes via backticks.
    """
    return SymbolID(
        scheme=SCHEME,
        descriptors=(
            Descriptor(name="api", kind=DescriptorKind.NAMESPACE),
            Descriptor(name=method, kind=DescriptorKind.TYPE),
            Descriptor(name=path, kind=DescriptorKind.TERM),
        ),
    )


__all__ = ["SCHEME", "HttpRouteBridge"]
