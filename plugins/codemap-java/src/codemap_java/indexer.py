"""Java indexer built on tree-sitter-java.

Covers class / interface / enum / record / method / constructor / field
declarations. Package declarations are honoured as a namespace prefix
under the file path. Nested types track a class stack to produce the
correct ``Cls#Inner#m()`` chain.

The indexer is single-file by design; cross-file `extends` / `implements`
resolution lives in a future bridge so the indexer surface stays narrow.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_java

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-java"
LANG = "java"

_JAVA_LANG = tree_sitter.Language(tree_sitter_java.language())

_TYPE_DECLS = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)


class JavaIndexer:
    name: ClassVar[str] = "java"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.java"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".java"

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
                        code="JAVA002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_JAVA_LANG)
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
                    code="JAVA001",
                    message="tree-sitter reported parse errors; symbols may be incomplete",
                    producer=self.name,
                )
            )
        return IndexResult(
            symbols=visitor.symbols,
            edges=visitor.edges,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------


class _Visitor:
    def __init__(self, relative_path: PurePosixPath) -> None:
        self.relative_path = relative_path
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.diagnostics: list[Diagnostic] = []
        self._class_stack: list[str] = []
        self._package: str = ""

    def visit(self, node: tree_sitter.Node) -> None:
        if node.type == "package_declaration":
            self._package = _node_text(node.children[1]) if node.child_count > 1 else ""
            return
        if node.type in _TYPE_DECLS:
            self._visit_type(node)
            return
        if node.type == "method_declaration" and self._class_stack:
            self._visit_method(node, is_constructor=False)
            return
        if node.type == "constructor_declaration" and self._class_stack:
            self._visit_method(node, is_constructor=True)
            return
        if node.type == "field_declaration" and self._class_stack:
            self._visit_field(node)
            return
        for child in node.children:
            self.visit(child)

    # ------------------------------------------------------------- types

    def _visit_type(self, node: tree_sitter.Node) -> None:
        name = _name_child(node)
        if name is None:
            return
        java_kind = node.type.removesuffix("_declaration")
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",  # Symbol schema has no separate interface/enum kind
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"java_kind": java_kind, "package": self._package}
                if self._package or java_kind != "class"
                else {},
            )
        )
        body = node.child_by_field_name("body")
        if body is None:
            return
        self._class_stack.append(name)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._class_stack.pop()

    # ----------------------------------------------------------- members

    def _visit_method(self, node: tree_sitter.Node, *, is_constructor: bool) -> None:
        name = _name_child(node)
        if name is None:
            return
        if is_constructor:
            display = "<init>"
            sid = self._make_id(display, kind=DescriptorKind.METHOD)
        else:
            display = name
            sid = self._make_id(name, kind=DescriptorKind.METHOD)
        signature = _method_signature(node, name, is_constructor=is_constructor)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=signature,
            )
        )

    def _visit_field(self, node: tree_sitter.Node) -> None:
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            name = _node_text(name_node)
            if not name:
                continue
            sid = self._make_id(name, kind=DescriptorKind.TERM)
            self.symbols.append(
                Symbol(
                    id=sid,
                    kind="field",
                    language=LANG,
                    file=self.relative_path,
                    range=_node_range(child),
                )
            )

    # ----------------------------------------------------------- helpers

    def _make_id(self, name: str, *, kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(
            Descriptor(name=cls, kind=DescriptorKind.TYPE) for cls in self._class_stack
        )
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


def _name_child(node: tree_sitter.Node) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.text is None:
        return None
    text = _node_text(name_node).strip()
    return text or None


def _method_signature(
    node: tree_sitter.Node,
    name: str,
    *,
    is_constructor: bool,
) -> str:
    params = node.child_by_field_name("parameters")
    params_text = _node_text(params) if params is not None else "()"
    if is_constructor:
        return f"{name}{params_text}"
    return_type = node.child_by_field_name("type")
    rt_text = _node_text(return_type) + " " if return_type is not None else ""
    return f"{rt_text}{name}{params_text}"
