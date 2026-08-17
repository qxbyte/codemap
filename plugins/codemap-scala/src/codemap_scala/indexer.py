"""Scala indexer built on tree-sitter-scala.

A leading ``package_clause`` (or multiple, for nested-package syntax)
prefixes every symbol with namespace descriptors. Classes / objects /
traits expose their template body so nested ``def`` / ``val`` / ``var``
members become methods/fields of the enclosing type.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_scala

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-scala"
LANG = "scala"

_SCALA_LANG = tree_sitter.Language(tree_sitter_scala.language())


class ScalaIndexer:
    name: ClassVar[str] = "scala"
    version: ClassVar[str] = package_version("codemap-scala")
    file_patterns: ClassVar[list[str]] = ["*.scala", "*.sc"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".scala", ".sc"}

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
                        code="SCALA002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_SCALA_LANG)
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
                    code="SCALA001",
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
        scope: list[Descriptor] = []
        for child in root.children:
            kind = child.type
            if kind == "package_clause":
                scope.extend(
                    Descriptor(name=part, kind=DescriptorKind.NAMESPACE)
                    for part in _package_parts(child)
                )
            else:
                self._visit(child, scope=scope)

    def _visit(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        kind = node.type
        if kind == "class_definition":
            scala_kind = "case_class" if _is_case(node) else "class"
            self._emit_type(node, scope=scope, scala_kind=scala_kind)
        elif kind == "object_definition":
            scala_kind = "case_object" if _is_case(node) else "object"
            self._emit_type(node, scope=scope, scala_kind=scala_kind)
        elif kind == "trait_definition":
            self._emit_type(node, scope=scope, scala_kind="trait")
        elif kind == "type_definition":
            self._emit_type_alias(node, scope=scope)
        elif kind in {"function_definition", "function_declaration"}:
            self._emit_method(node, scope=scope)
        elif kind == "val_definition":
            self._emit_value(node, scope=scope, scala_kind="val")
        elif kind == "var_definition":
            self._emit_value(node, scope=scope, scala_kind="var")

    def _emit_type(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
        scala_kind: str,
    ) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        type_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        descriptors = [*list(scope), type_desc]
        self.symbols.append(
            Symbol(
                id=self._make_id(descriptors),
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"scala_kind": scala_kind},
            )
        )
        # Case-class constructor parameters become fields.
        if scala_kind == "case_class":
            params = _first_child(node, "class_parameters")
            if params is not None:
                for child in params.children:
                    if child.type == "class_parameter":
                        pname = _first_child_text(child, "identifier")
                        if pname is None:
                            continue
                        self.symbols.append(
                            Symbol(
                                id=self._make_id(
                                    [
                                        *list(descriptors),
                                        Descriptor(name=pname, kind=DescriptorKind.TERM),
                                    ]
                                ),
                                kind="field",
                                language=LANG,
                                file=self.relative_path,
                                range=_node_range(child),
                                extra={"scala_kind": "case_field"},
                            )
                        )
        # Walk the template body for nested members.
        body = _first_child(node, "template_body")
        if body is None:
            return
        for child in body.children:
            self._visit(child, scope=descriptors)

    def _emit_type_alias(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "type_identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), Descriptor(name=name, kind=DescriptorKind.TYPE)]),
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"scala_kind": "type"},
            )
        )

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

    def _emit_value(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
        scala_kind: str,
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
                extra={"scala_kind": scala_kind},
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


def _is_case(node: tree_sitter.Node) -> bool:
    return any(child.type == "case" for child in node.children)


def _package_parts(node: tree_sitter.Node) -> list[str]:
    ident_node = _first_child(node, "package_identifier")
    if ident_node is None:
        # Fallback: single identifier under package_clause.
        return [_node_text(c) for c in node.children if c.type == "identifier"]
    return [_node_text(c) for c in ident_node.children if c.type == "identifier"]
