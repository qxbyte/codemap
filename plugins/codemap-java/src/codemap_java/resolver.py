"""JavaCallResolverBridge — cross-file FQN-based call/extends/implements resolver.

Consumes the metadata that :class:`codemap_java.indexer.JavaIndexer` attaches
to ``Symbol.extra``:

* top-level class symbols carry ``package`` / ``imports`` / ``supertypes``
* method symbols carry ``params`` (list of ``{name, type}``) and
  ``pending_calls`` (raw invocation records — receiver text, method name,
  argument arity, location)
* field symbols carry ``type``

Algorithm (single bridge pass, ADR-0013):

1. Build a project-wide FQN table from all top-level Java classes
   (``package + simple_name``).
2. Index each class's methods (by name → list of (arity, sid)) and fields
   (by name → type string), so we can dispatch later by arity and follow
   field receivers to their declared types.
3. Resolve each class's ``supertypes`` against ``imports`` + same-package
   + java.lang implicit imports, emit ``extends`` / ``implements`` edges.
4. For each pending invocation, infer the receiver class's FQN
   (``""``/``"this"``/``"super"`` → caller class; capitalised → resolve as
   type; lowercase → look up caller's field of that name and take its
   declared type), then emit a ``calls`` edge iff exactly one method on
   the target class matches by name + arity. Ambiguous / unresolved
   invocations silently drop — they aren't crashes.

All edges are emitted with ``confidence="medium"`` per ADR-0013's accepted
trade-off versus full semantic resolution.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, ClassVar

from codemap.core.models import BridgeResult, Edge
from codemap.core.store import ReadOnlyStore
from codemap.core.symbol import DescriptorKind, SymbolID
from codemap_java._version import __version__

__all__ = ["JavaCallResolverBridge"]


class JavaCallResolverBridge:
    name: ClassVar[str] = "java_calls"
    version: ClassVar[str] = __version__
    requires: ClassVar[list[str]] = []

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        # One pass over the store to bucket java symbols.
        classes: list[Any] = []
        methods: list[Any] = []
        fields: list[Any] = []
        for sym in store.iter_symbols():
            if sym.language != "java":
                continue
            if sym.kind == "class" and "imports" in sym.extra:
                # Top-level only. (Nested classes don't carry imports; the
                # current resolver doesn't follow them — see ADR-0013.)
                classes.append(sym)
            elif sym.kind == "method":
                methods.append(sym)
            elif sym.kind == "field":
                fields.append(sym)

        # Build FQN table + per-class info.
        fqn_to_sid: dict[str, SymbolID] = {}
        simple_to_fqn: dict[str, list[str]] = defaultdict(list)
        info_by_sid: dict[SymbolID, _ClassInfo] = {}
        file_to_classes: dict[PurePosixPath, list[_ClassInfo]] = defaultdict(list)

        for cls in classes:
            pkg = str(cls.extra.get("package", ""))
            simple = cls.id.descriptors[-1].name
            fqn = f"{pkg}.{simple}" if pkg else simple
            fqn_to_sid[fqn] = cls.id
            simple_to_fqn[simple].append(fqn)
            info = _ClassInfo(
                sid=cls.id,
                fqn=fqn,
                pkg=pkg,
                simple_name=simple,
                file=cls.file,
                imports=list(cls.extra.get("imports", [])),
                supertypes=list(cls.extra.get("supertypes", [])),
            )
            info_by_sid[cls.id] = info
            file_to_classes[cls.file].append(info)

        # Attach methods + fields to their owner class.
        for m in methods:
            owner = _owner_class(m, file_to_classes)
            if owner is None:
                continue
            arity = len(m.extra.get("params", []))
            owner.methods[m.id.descriptors[-1].name].append(
                _MethodRecord(
                    sid=m.id,
                    arity=arity,
                    pending_calls=list(m.extra.get("pending_calls", [])),
                )
            )
        for f in fields:
            owner = _owner_class(f, file_to_classes)
            if owner is None:
                continue
            ftype = str(f.extra.get("type", "")).strip()
            if ftype:
                owner.fields[f.id.descriptors[-1].name] = ftype

        # Resolver helpers in closure.
        def resolve_type(name: str, ctx: _ClassInfo) -> str | None:
            if "." in name:
                return name if name in fqn_to_sid else None
            same_pkg = f"{ctx.pkg}.{name}" if ctx.pkg else name
            if same_pkg in fqn_to_sid:
                return same_pkg
            for imp in ctx.imports:
                if imp.endswith(".*"):
                    candidate = f"{imp[:-2]}.{name}"
                    if candidate in fqn_to_sid:
                        return candidate
                elif imp.rsplit(".", 1)[-1] == name and imp in fqn_to_sid:
                    return imp
            # java.lang implicit
            implicit = f"java.lang.{name}"
            if implicit in fqn_to_sid:
                return implicit
            # Last resort: unique simple-name match across the project.
            candidates = simple_to_fqn.get(name, [])
            if len(candidates) == 1:
                return candidates[0]
            return None

        edges: list[Edge] = []

        # extends / implements edges.
        for info in info_by_sid.values():
            for sup in info.supertypes:
                tgt_fqn = resolve_type(sup["name"], info)
                if tgt_fqn is None:
                    continue
                edges.append(
                    Edge(
                        source=info.sid,
                        target=fqn_to_sid[tgt_fqn],
                        kind=sup["relation"],  # "extends" | "implements"
                        confidence="medium",
                    )
                )

        # calls edges.
        for info in info_by_sid.values():
            for records in info.methods.values():
                for rec in records:
                    for call in rec.pending_calls:
                        tgt_sid = _resolve_call(call, info, resolve_type, fqn_to_sid, info_by_sid)
                        if tgt_sid is None:
                            continue
                        edges.append(
                            Edge(
                                source=rec.sid,
                                target=tgt_sid,
                                kind="calls",
                                confidence="medium",
                            )
                        )

        return BridgeResult(edges=edges)


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class _ClassInfo:
    __slots__ = (
        "fields",
        "file",
        "fqn",
        "imports",
        "methods",
        "pkg",
        "sid",
        "simple_name",
        "supertypes",
    )

    def __init__(
        self,
        *,
        sid: SymbolID,
        fqn: str,
        pkg: str,
        simple_name: str,
        file: PurePosixPath,
        imports: list[str],
        supertypes: list[dict[str, str]],
    ) -> None:
        self.sid = sid
        self.fqn = fqn
        self.pkg = pkg
        self.simple_name = simple_name
        self.file = file
        self.imports = imports
        self.supertypes = supertypes
        self.methods: dict[str, list[_MethodRecord]] = defaultdict(list)
        self.fields: dict[str, str] = {}


class _MethodRecord:
    __slots__ = ("arity", "pending_calls", "sid")

    def __init__(
        self,
        *,
        sid: SymbolID,
        arity: int,
        pending_calls: list[dict[str, Any]],
    ) -> None:
        self.sid = sid
        self.arity = arity
        self.pending_calls = pending_calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owner_class(
    sym: Any,
    file_to_classes: dict[PurePosixPath, list[_ClassInfo]],
) -> _ClassInfo | None:
    """Locate the top-level class that owns ``sym`` (a method or field).

    Owner is the class whose simple name matches the second-to-last
    descriptor of ``sym.id`` and lives in the same file.
    """
    descs = sym.id.descriptors
    if len(descs) < 2 or descs[-2].kind is not DescriptorKind.TYPE:
        return None
    owner_name = descs[-2].name
    for info in file_to_classes.get(sym.file, []):
        if info.simple_name == owner_name:
            return info
    return None


def _resolve_call(
    call: dict[str, Any],
    caller: _ClassInfo,
    resolve_type,  # type: ignore[no-untyped-def]
    fqn_to_sid: dict[str, SymbolID],
    info_by_sid: dict[SymbolID, _ClassInfo],
) -> SymbolID | None:
    receiver = str(call.get("receiver", ""))
    name = str(call.get("name", ""))
    arity = int(call.get("arity", 0))
    if not name:
        return None

    if receiver in {"", "this", "super"}:
        target_fqn: str | None = caller.fqn
    elif receiver and receiver[0].isupper():
        target_fqn = resolve_type(receiver, caller)
    else:
        ftype = caller.fields.get(receiver)
        target_fqn = resolve_type(ftype, caller) if ftype else None

    if target_fqn is None:
        return None
    target_cls_sid = fqn_to_sid.get(target_fqn)
    if target_cls_sid is None:
        return None
    target_info = info_by_sid.get(target_cls_sid)
    if target_info is None:
        return None

    candidates = [m.sid for m in target_info.methods.get(name, []) if m.arity == arity]
    if len(candidates) == 1:
        return candidates[0]
    return None
