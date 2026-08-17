"""MyBatisLinkBridge — link sql_mapping symbols back to their Java Mapper methods.

Runs after both ``codemap-java`` and ``codemap-mybatis`` indexers have
populated the store. For every ``sql_mapping`` symbol carrying
``java_namespace`` + ``java_method_name`` in its ``extra``, look up the Java
method symbol whose owner class FQN matches the namespace and whose own
simple name matches the statement id. Emit a ``maps_to`` edge
``java_method → sql_mapping`` so call-graph queries can hop from caller
code through the XML statement to the table it accesses.

No fuzzy matching: namespace and method name must both be exact. Overloads
(same simple name, different arity) yield multiple edges — confidence
``medium`` for every hit because we cannot pick the Java method overload
that the mapper interface declares without parsing the interface itself
(which is also already in the store, but parameter-typed matching is out
of scope for v1).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, ClassVar

from codemap.core.models import BridgeResult, Edge
from codemap.core.store import ReadOnlyStore
from codemap.core.symbol import DescriptorKind, SymbolID
from codemap.plugin_metadata import package_version

__all__ = ["MyBatisLinkBridge"]


class MyBatisLinkBridge:
    name: ClassVar[str] = "mybatis_link"
    version: ClassVar[str] = package_version("codemap-mybatis")
    requires: ClassVar[list[str]] = []

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        sql_mappings: list[Any] = []
        java_methods_by_owner: dict[str, list[Any]] = defaultdict(list)
        java_classes_by_fqn: dict[str, Any] = {}

        for sym in store.iter_symbols():
            if sym.kind == "sql_mapping" and sym.extra.get("java_namespace"):
                sql_mappings.append(sym)
            elif sym.language == "java" and sym.kind == "class" and "imports" in sym.extra:
                pkg = str(sym.extra.get("package", ""))
                simple = sym.id.descriptors[-1].name
                fqn = f"{pkg}.{simple}" if pkg else simple
                java_classes_by_fqn[fqn] = sym
            elif sym.language == "java" and sym.kind == "method":
                descs = sym.id.descriptors
                if len(descs) >= 2 and descs[-2].kind is DescriptorKind.TYPE:
                    java_methods_by_owner[descs[-2].name].append(sym)

        edges: list[Edge] = []
        for mapping in sql_mappings:
            ns = str(mapping.extra.get("java_namespace", ""))
            mname = str(mapping.extra.get("java_method_name", ""))
            if not ns or not mname:
                continue
            owner_cls = java_classes_by_fqn.get(ns)
            if owner_cls is None:
                continue
            owner_simple = owner_cls.id.descriptors[-1].name
            for method_sym in java_methods_by_owner.get(owner_simple, []):
                if method_sym.id.descriptors[-1].name != mname:
                    continue
                if method_sym.file != owner_cls.file:
                    # different owner class with the same simple name
                    continue
                edges.append(
                    Edge(
                        source=method_sym.id,
                        target=_to_sid(mapping.id),
                        kind="maps_to",
                        confidence="medium",
                    )
                )
        return BridgeResult(edges=edges)


def _to_sid(sid: SymbolID) -> SymbolID:
    """Re-tag identity helper, kept so the bridge module is the only place
    that imports SymbolID in case the conversion ever needs a tweak."""
    return sid
