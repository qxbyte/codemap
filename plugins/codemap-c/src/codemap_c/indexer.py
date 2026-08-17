"""C indexer built on tree-sitter-c.

Top-level declarations only (function bodies are not walked for inner
state). Captured node kinds:

* ``function_definition``                       → ``function``
* ``struct_specifier`` / ``union_specifier``     → ``class`` (with body)
* ``enum_specifier``                             → ``class``
* ``type_definition`` (``typedef``)              → ``class``
* ``preproc_def`` / ``preproc_function_def``     → ``variable`` (macro)
* top-level ``declaration`` with initializer     → ``variable``
* ``field_declaration`` inside struct/union body → ``field``
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_c

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-c"
LANG = "c"

_C_LANG = tree_sitter.Language(tree_sitter_c.language())


class CIndexer:
    name: ClassVar[str] = "c"
    version: ClassVar[str] = package_version("codemap-c")
    file_patterns: ClassVar[list[str]] = ["*.c", "*.h"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".c", ".h"}

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
                        code="C002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_C_LANG)
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
                    code="C001",
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
            self._visit_top_level(child)

    def _visit_top_level(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "function_definition":
            self._emit_function(node)
        elif kind == "preproc_def":
            self._emit_macro(node, function_like=False)
        elif kind == "preproc_function_def":
            self._emit_macro(node, function_like=True)
        elif kind == "type_definition":
            self._emit_typedef(node)
        elif kind == "struct_specifier":
            self._emit_record(node, c_kind="struct")
        elif kind == "union_specifier":
            self._emit_record(node, c_kind="union")
        elif kind == "enum_specifier":
            self._emit_enum(node)
        elif kind == "declaration":
            self._emit_declaration(node)

    def _emit_function(self, node: tree_sitter.Node) -> None:
        name = _function_declarator_name(node)
        if name is None:
            return
        sid = self._make_id([Descriptor(name=name, kind=DescriptorKind.METHOD)])
        self.symbols.append(
            Symbol(
                id=sid,
                kind="function",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"{name}()",
            )
        )

    def _emit_macro(self, node: tree_sitter.Node, *, function_like: bool) -> None:
        name = _first_child_text(node, "identifier")
        if name is None:
            return
        sid = self._make_id([Descriptor(name=name, kind=DescriptorKind.TERM)])
        extra = {"c_kind": "macro_fn" if function_like else "macro"}
        self.symbols.append(
            Symbol(
                id=sid,
                kind="variable",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra=extra,
            )
        )

    def _emit_typedef(self, node: tree_sitter.Node) -> None:
        # The aliased name is the last type_identifier child of the
        # type_definition.
        name: str | None = None
        for child in node.children:
            if child.type == "type_identifier":
                name = _node_text(child)
        if name is None:
            return
        sid = self._make_id([Descriptor(name=name, kind=DescriptorKind.TYPE)])
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"c_kind": "typedef"},
            )
        )

    def _emit_record(self, node: tree_sitter.Node, *, c_kind: str) -> None:
        # Skip anonymous structs / forward declarations without a body.
        name = _first_child_text(node, "type_identifier")
        body = _first_child(node, "field_declaration_list")
        if name is None or body is None:
            return
        record_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        sid = self._make_id([record_desc])
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"c_kind": c_kind},
            )
        )
        for child in body.children:
            if child.type == "field_declaration":
                self._emit_field(child, parent=record_desc)

    def _emit_enum(self, node: tree_sitter.Node) -> None:
        name = _first_child_text(node, "type_identifier")
        if name is None:
            return
        enum_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        sid = self._make_id([enum_desc])
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"c_kind": "enum"},
            )
        )
        body = _first_child(node, "enumerator_list")
        if body is None:
            return
        for child in body.children:
            if child.type == "enumerator":
                enum_name = _first_child_text(child, "identifier")
                if enum_name is None:
                    continue
                self.symbols.append(
                    Symbol(
                        id=self._make_id(
                            [
                                enum_desc,
                                Descriptor(name=enum_name, kind=DescriptorKind.TERM),
                            ]
                        ),
                        kind="field",
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(child),
                        extra={"c_kind": "enumerator"},
                    )
                )

    def _emit_field(
        self,
        node: tree_sitter.Node,
        *,
        parent: Descriptor,
    ) -> None:
        name = _first_child_text(node, "field_identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([parent, Descriptor(name=name, kind=DescriptorKind.TERM)]),
                kind="field",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
            )
        )

    def _emit_declaration(self, node: tree_sitter.Node) -> None:
        # Only emit when there's an init_declarator (i.e. a definition with
        # a value), not a bare extern prototype.
        for child in node.children:
            if child.type == "init_declarator":
                name = _first_child_text(child, "identifier")
                if name is None:
                    continue
                self.symbols.append(
                    Symbol(
                        id=self._make_id([Descriptor(name=name, kind=DescriptorKind.TERM)]),
                        kind="variable",
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(node),
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


def _function_declarator_name(node: tree_sitter.Node) -> str | None:
    """``int add(int, int) { ... }`` → ``add``. The function_declarator may
    be wrapped in pointers (``int *foo(...)``), so unwrap recursively.
    """
    declarator = _first_child(node, "function_declarator")
    if declarator is None:
        # Walk through pointer_declarator wrappers.
        for child in node.children:
            if child.type in {"pointer_declarator", "parenthesized_declarator"}:
                name = _function_declarator_name(child)
                if name is not None:
                    return name
        return None
    return _first_child_text(declarator, "identifier")
