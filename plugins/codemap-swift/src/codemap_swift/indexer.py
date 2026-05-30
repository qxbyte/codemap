"""Swift indexer built on tree-sitter-swift.

Swift's tree-sitter grammar uses a single ``class_declaration`` node to
cover ``class``, ``struct``, and ``enum`` declarations. The keyword
itself is the first child token of the node, so we read it to fill in
``extra.swift_kind``. ``protocol_declaration`` is a separate node type.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_swift

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-swift"
LANG = "swift"

_SWIFT_LANG = tree_sitter.Language(tree_sitter_swift.language())


class SwiftIndexer:
    name: ClassVar[str] = "swift"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.swift"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".swift"

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
                        code="SW002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_SWIFT_LANG)
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
                    code="SW001",
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

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "class_declaration":
            self._visit_class_like(node)
            return
        if kind == "protocol_declaration":
            self._visit_type(node, swift_kind="protocol", body_field="body")
            return
        if kind == "function_declaration":
            self._visit_function(node)
            return
        if kind == "init_declaration":
            self._visit_init(node)
            return
        if kind == "property_declaration":
            self._visit_property(node)
            return
        for child in node.children:
            self.visit(child)

    # ----------------------------------------------------- types

    def _visit_class_like(self, node: tree_sitter.Node) -> None:
        swift_kind = _first_keyword(node) or "class"
        self._visit_type(node, swift_kind=swift_kind, body_field=None)

    def _visit_type(
        self,
        node: tree_sitter.Node,
        *,
        swift_kind: str,
        body_field: str | None,
    ) -> None:
        name = _first_type_identifier(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"swift_kind": swift_kind},
            )
        )
        body = node.child_by_field_name(body_field) if body_field else _find_body(node)
        if body is None:
            return
        self._type_stack.append(name)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._type_stack.pop()

    # --------------------------------------------------- functions

    def _visit_function(self, node: tree_sitter.Node) -> None:
        name = _simple_identifier(node)
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
                signature=f"func {name}()",
            )
        )

    def _visit_init(self, node: tree_sitter.Node) -> None:
        if not self._type_stack:
            return
        sid = self._make_id("init", kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature="init()",
            )
        )

    # ---------------------------------------------------- properties

    def _visit_property(self, node: tree_sitter.Node) -> None:
        # property_declaration > pattern > simple_identifier (name)
        for child in node.children:
            if child.type == "pattern":
                for grand in child.children:
                    if grand.type == "simple_identifier":
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


def _first_keyword(node: tree_sitter.Node) -> str | None:
    """Return the first keyword token (class/struct/enum) for class_declaration."""
    for child in node.children:
        if child.type in {"class", "struct", "enum", "actor"}:
            return child.type
    return None


def _first_type_identifier(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "type_identifier":
            return _node_text(child)
    return None


def _simple_identifier(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "simple_identifier":
            return _node_text(child)
    return None


def _find_body(node: tree_sitter.Node) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type in {"class_body", "enum_class_body", "protocol_body"}:
            return child
    return None
