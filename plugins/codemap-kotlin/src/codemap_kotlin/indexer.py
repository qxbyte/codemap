"""Kotlin indexer built on tree-sitter-kotlin.

The Kotlin grammar uses ``class_declaration`` for both ``class`` and
``interface``. The keyword token disambiguates. ``object_declaration``
is its own node type for singleton objects.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_kotlin

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-kotlin"
LANG = "kotlin"

_KT_LANG = tree_sitter.Language(tree_sitter_kotlin.language())


class KotlinIndexer:
    name: ClassVar[str] = "kotlin"
    version: ClassVar[str] = package_version("codemap-kotlin")
    file_patterns: ClassVar[list[str]] = ["*.kt", "*.kts"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".kt", ".kts"}

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
                        code="KT002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_KT_LANG)
        tree = parser.parse(source)
        visitor = _Visitor(ctx.relative_path)
        visitor.visit(tree.root_node)
        diagnostics = list(visitor.diagnostics)
        if tree.root_node.has_error:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    file=ctx.relative_path,
                    range=Range(start_line=1, end_line=1),
                    code="KT001",
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
        self._type_stack: list[str] = []
        self._package: str = ""

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "package_header":
            self._set_package(node)
            return
        if kind == "class_declaration":
            self._visit_class_or_interface(node)
            return
        if kind == "object_declaration":
            self._visit_object(node)
            return
        if kind == "function_declaration":
            self._visit_function(node)
            return
        if kind == "property_declaration":
            self._visit_property(node)
            return
        for child in node.children:
            self.visit(child)

    # ----------------------------------------------------- packages

    def _set_package(self, node: tree_sitter.Node) -> None:
        for child in node.children:
            if child.type == "qualified_identifier":
                self._package = _node_text(child)
                return
            if child.type == "identifier":
                self._package = _node_text(child)
                return

    # --------------------------------------------------- type-level

    def _visit_class_or_interface(self, node: tree_sitter.Node) -> None:
        kotlin_kind = "class"
        for child in node.children:
            if child.type == "interface":
                kotlin_kind = "interface"
                break
        self._visit_type(node, kotlin_kind=kotlin_kind)

    def _visit_object(self, node: tree_sitter.Node) -> None:
        self._visit_type(node, kotlin_kind="object")

    def _visit_type(self, node: tree_sitter.Node, *, kotlin_kind: str) -> None:
        name = _first_identifier(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        extra: dict[str, str] = {"kotlin_kind": kotlin_kind}
        if self._package:
            extra["package"] = self._package
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra=extra,
            )
        )
        body = _find_class_body(node)
        if body is None:
            return
        self._type_stack.append(name)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._type_stack.pop()

    # ----------------------------------------------------- functions

    def _visit_function(self, node: tree_sitter.Node) -> None:
        name = _first_identifier(node)
        if name is None:
            return
        kind: str = "method" if self._type_stack else "function"
        sid = self._make_id(name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind=kind,  # type: ignore[arg-type]
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"fun {name}()",
            )
        )

    # ---------------------------------------------------- properties

    def _visit_property(self, node: tree_sitter.Node) -> None:
        # property_declaration > variable_declaration > identifier
        for child in node.children:
            if child.type == "variable_declaration":
                for grand in child.children:
                    if grand.type == "identifier":
                        name = _node_text(grand)
                        if not name:
                            return
                        sym_kind: str = "field" if self._type_stack else "variable"
                        sid = self._make_id(name, kind=DescriptorKind.TERM)
                        self.symbols.append(
                            Symbol(
                                id=sid,
                                kind=sym_kind,  # type: ignore[arg-type]
                                language=LANG,
                                file=self.relative_path,
                                range=_node_range(node),
                            )
                        )
                        return

    # -------------------------------------------------------- helpers

    def _make_id(self, name: str, *, kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(Descriptor(name=t, kind=DescriptorKind.TYPE) for t in self._type_stack)
        descriptors.append(Descriptor(name=name, kind=kind))
        return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))


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


def _first_identifier(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child)
    return None


def _find_class_body(node: tree_sitter.Node) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type == "class_body":
            return child
    return None
