"""C# indexer built on tree-sitter-c-sharp.

``namespace_declaration`` chains (including dotted ``A.B.C`` qualifiers)
are decomposed into a stack of namespace descriptors that prefix each
contained type's SymbolID.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_c_sharp

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-csharp"
LANG = "csharp"

_CS_LANG = tree_sitter.Language(tree_sitter_c_sharp.language())

_TYPE_DECL_KINDS = {
    "class_declaration": (None, "class"),
    "interface_declaration": ("interface", "class"),
    "struct_declaration": ("struct", "class"),
    "record_declaration": ("record", "class"),
    "enum_declaration": ("enum", "class"),
    "delegate_declaration": ("delegate", "class"),
}


class CSharpIndexer:
    name: ClassVar[str] = "csharp"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.cs", "*.csx"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".cs", ".csx"}

    def index_file(
        self,
        path: Path,
        source: bytes,
        ctx: IndexContext,
    ) -> IndexResult:
        try:
            source.decode("utf-8")
        except UnicodeDecodeError as exc:
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        file=ctx.relative_path,
                        code="CS002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_CS_LANG)
        tree = parser.parse(source)
        visitor = _Visitor(ctx.relative_path)
        visitor.visit_root(tree.root_node)
        diagnostics = list(visitor.diagnostics)
        if tree.root_node.has_error:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    file=ctx.relative_path,
                    range=Range(start_line=1, end_line=1),
                    code="CS001",
                    message="tree-sitter reported parse errors; symbols may be incomplete",
                    producer=self.name,
                )
            )
        return IndexResult(
            symbols=visitor.symbols,
            edges=visitor.edges,
            diagnostics=diagnostics,
        )


class _Visitor:
    def __init__(self, relative_path: PurePosixPath) -> None:
        self.relative_path = relative_path
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.diagnostics: list[Diagnostic] = []

    def visit_root(self, root: tree_sitter.Node) -> None:
        for child in root.children:
            self._visit(child, scope=[])

    def _visit(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        kind = node.type
        if kind == "namespace_declaration":
            self._visit_namespace(node, scope=scope)
        elif kind in _TYPE_DECL_KINDS:
            csharp_kind, symbol_kind = _TYPE_DECL_KINDS[kind]
            self._emit_type(
                node,
                scope=scope,
                csharp_kind=csharp_kind,
                symbol_kind=symbol_kind,
            )
        elif kind == "method_declaration":
            self._emit_method(node, scope=scope)
        elif kind == "property_declaration":
            self._emit_property(node, scope=scope)
        elif kind == "field_declaration":
            self._emit_field_declaration(node, scope=scope)
        elif kind == "enum_member_declaration":
            self._emit_enum_member(node, scope=scope)

    def _visit_namespace(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        new_scope = list(scope)
        for child in node.children:
            if child.type == "identifier":
                new_scope.append(Descriptor(name=_node_text(child), kind=DescriptorKind.NAMESPACE))
            elif child.type == "qualified_name":
                new_scope.extend(
                    Descriptor(name=part, kind=DescriptorKind.NAMESPACE)
                    for part in _qualified_name_parts(child)
                )
        body = _first_child(node, "declaration_list")
        if body is None:
            return
        for child in body.children:
            self._visit(child, scope=new_scope)

    def _emit_type(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
        csharp_kind: str | None,
        symbol_kind: str,
    ) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        type_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        descriptors = [*list(scope), type_desc]
        extra: dict[str, str] = {}
        if csharp_kind is not None:
            extra["csharp_kind"] = csharp_kind
        self.symbols.append(
            Symbol(
                id=self._make_id(descriptors),
                kind=symbol_kind,
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra=extra,
            )
        )
        # Recurse into nested members.
        body = _first_child(node, "declaration_list") or _first_child(
            node, "enum_member_declaration_list"
        )
        if body is None:
            return
        for child in body.children:
            self._visit(child, scope=descriptors)

    def _emit_method(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), Descriptor(name=name, kind=DescriptorKind.METHOD)]),
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"{name}()",
            )
        )

    def _emit_property(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), Descriptor(name=name, kind=DescriptorKind.TERM)]),
                kind="field",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"csharp_kind": "property"},
            )
        )

    def _emit_field_declaration(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        var_decl = _first_child(node, "variable_declaration")
        if var_decl is None:
            return
        for child in var_decl.children:
            if child.type == "variable_declarator":
                name = _first_child_text(child, "identifier")
                if name is None:
                    continue
                self.symbols.append(
                    Symbol(
                        id=self._make_id(
                            [*list(scope), Descriptor(name=name, kind=DescriptorKind.TERM)]
                        ),
                        kind="field",
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(node),
                    )
                )

    def _emit_enum_member(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), Descriptor(name=name, kind=DescriptorKind.TERM)]),
                kind="field",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"csharp_kind": "enum_member"},
            )
        )

    def _make_id(self, descriptors: list[Descriptor]) -> SymbolID:
        full = list(_path_namespaces(self.relative_path))
        full.extend(descriptors)
        return SymbolID(scheme=SCHEME, descriptors=tuple(full))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _path_namespaces(path: PurePosixPath) -> list[Descriptor]:
    return [Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in path.parts]


def _node_range(node: tree_sitter.Node) -> Range:
    sr, sc = node.start_point
    er, ec = node.end_point
    return Range(
        start_line=sr + 1,
        start_col=sc,
        end_line=max(er + 1, sr + 1),
        end_col=ec,
    )


def _node_text(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""


def _first_child(node: tree_sitter.Node, kind: str) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type == kind:
            return child
    return None


def _first_child_text(node: tree_sitter.Node, kind: str) -> str | None:
    found = _first_child(node, kind)
    return _node_text(found) if found is not None else None


def _qualified_name_parts(node: tree_sitter.Node) -> list[str]:
    parts: list[str] = []
    for child in node.children:
        if child.type == "identifier":
            parts.append(_node_text(child))
        elif child.type == "qualified_name":
            parts.extend(_qualified_name_parts(child))
    return parts
