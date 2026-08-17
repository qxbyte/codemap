"""PHP indexer built on tree-sitter-php.

Handles all four PHP type declarations (``class`` / ``interface`` /
``trait`` / ``enum``) with their respective bodies, plus free
``function_definition`` and module-level ``const_declaration``.
``namespace_definition`` is honoured as ``extra.namespace`` on every
type symbol; nested types share the same single namespace (PHP doesn't
allow nested classes the way Java does, but the tree-sitter grammar
permits it).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_php

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap_php._version import __version__

SCHEME = "scip-php"
LANG = "php"

_PHP_LANG = tree_sitter.Language(tree_sitter_php.language_php())

_TYPE_DECLS: dict[str, str] = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "trait_declaration": "trait",
    "enum_declaration": "enum",
}


class PhpIndexer:
    name: ClassVar[str] = "php"
    version: ClassVar[str] = __version__
    file_patterns: ClassVar[list[str]] = ["*.php"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".php"

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
                        code="PHP002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_PHP_LANG)
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
                    code="PHP001",
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
        self._namespace: str = ""

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "namespace_definition":
            self._set_namespace(node)
            return
        if kind in _TYPE_DECLS:
            self._visit_type(node, php_kind=_TYPE_DECLS[kind])
            return
        if kind == "function_definition":
            self._visit_function(node)
            return
        if kind == "method_declaration" and self._type_stack:
            self._visit_method(node)
            return
        if kind == "property_declaration" and self._type_stack:
            self._visit_property(node)
            return
        if kind == "const_declaration":
            self._visit_const(node)
            return
        for child in node.children:
            self.visit(child)

    # ------------------------------------------------- namespace

    def _set_namespace(self, node: tree_sitter.Node) -> None:
        for child in node.children:
            if child.type == "namespace_name":
                self._namespace = _node_text(child)
                return

    # ------------------------------------------------------- types

    def _visit_type(self, node: tree_sitter.Node, *, php_kind: str) -> None:
        name = _name_child(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        extra: dict[str, str] = {"php_kind": php_kind}
        if self._namespace:
            extra["namespace"] = self._namespace
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
        body = _declaration_list(node)
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
        if self._type_stack:
            # Function defined inside a class body (rare but legal in some
            # grammars) — treat as method.
            self._visit_method(node)
            return
        name = _name_child(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="function",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"function {name}()",
            )
        )

    def _visit_method(self, node: tree_sitter.Node) -> None:
        name = _name_child(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"function {name}()",
            )
        )

    # --------------------------------------------------- properties

    def _visit_property(self, node: tree_sitter.Node) -> None:
        # property_declaration > property_element > variable_name
        for child in node.children:
            if child.type == "property_element":
                for grand in child.children:
                    if grand.type == "variable_name":
                        # variable_name has a single name child (without '$')
                        for great in grand.children:
                            if great.type == "name":
                                name = _node_text(great)
                                if not name:
                                    return
                                sid = self._make_id(name, kind=DescriptorKind.TERM)
                                self.symbols.append(
                                    Symbol(
                                        id=sid,
                                        kind="field",
                                        language=LANG,
                                        file=self.relative_path,
                                        range=_node_range(node),
                                    )
                                )
                                return

    # ------------------------------------------------ const decls

    def _visit_const(self, node: tree_sitter.Node) -> None:
        # const_declaration > const_element > name
        for child in node.children:
            if child.type != "const_element":
                continue
            for grand in child.children:
                if grand.type == "name":
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


def _name_child(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "name":
            return _node_text(child)
    return None


def _declaration_list(node: tree_sitter.Node) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type in {"declaration_list", "enum_declaration_list"}:
            return child
    return None
