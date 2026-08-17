"""C++ indexer built on tree-sitter-cpp.

The visitor recurses into ``namespace_definition`` so that descriptors of
nested types are prefixed with the containing namespace chain.
``template_declaration`` wrappers are unwrapped so the underlying
function / class / struct surfaces as a normal symbol.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_cpp

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-cpp"
LANG = "cpp"

_CPP_LANG = tree_sitter.Language(tree_sitter_cpp.language())


class CppIndexer:
    name: ClassVar[str] = "cpp"
    version: ClassVar[str] = package_version("codemap-cpp")
    file_patterns: ClassVar[list[str]] = [
        "*.cpp",
        "*.cc",
        "*.cxx",
        "*.hpp",
        "*.hh",
        "*.hxx",
    ]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"}

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
                        code="CPP002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_CPP_LANG)
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
                    code="CPP001",
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
        if kind == "namespace_definition":
            self._visit_namespace(node, scope=scope)
        elif kind == "template_declaration":
            # Unwrap: a template is metadata around a single declaration.
            inner = _template_inner(node)
            if inner is not None:
                self._visit(inner, scope=scope)
        elif kind == "function_definition":
            self._emit_function(node, scope=scope, container_kind=None)
        elif kind == "class_specifier":
            self._emit_record(node, scope=scope, cpp_kind="class")
        elif kind == "struct_specifier":
            self._emit_record(node, scope=scope, cpp_kind="struct")
        elif kind == "union_specifier":
            self._emit_record(node, scope=scope, cpp_kind="union")
        elif kind == "enum_specifier":
            self._emit_enum(node, scope=scope)

    def _visit_namespace(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "namespace_identifier")
        new_scope = list(scope)
        if name is not None:
            new_scope.append(Descriptor(name=name, kind=DescriptorKind.NAMESPACE))
        body = _first_child(node, "declaration_list")
        if body is None:
            return
        for child in body.children:
            self._visit(child, scope=new_scope)

    def _emit_function(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
        container_kind: str | None,
    ) -> None:
        name = _function_declarator_name(node)
        if name is None:
            return
        descriptors = [*list(scope), Descriptor(name=name, kind=DescriptorKind.METHOD)]
        kind = "method" if container_kind == "class" else "function"
        self.symbols.append(
            Symbol(
                id=self._make_id(descriptors),
                kind=kind,
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"{name}()",
            )
        )

    def _emit_record(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
        cpp_kind: str,
    ) -> None:
        name = _first_child_text(node, "type_identifier")
        body = _first_child(node, "field_declaration_list")
        if name is None or body is None:
            return
        record_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        descriptors = [*list(scope), record_desc]
        self.symbols.append(
            Symbol(
                id=self._make_id(descriptors),
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"cpp_kind": cpp_kind},
            )
        )
        inner_scope = list(descriptors)
        for child in body.children:
            if child.type == "function_definition":
                self._emit_function(child, scope=inner_scope, container_kind="class")
            elif child.type == "field_declaration":
                self._emit_field(child, scope=inner_scope)
            elif child.type == "template_declaration":
                inner = _template_inner(child)
                if inner is not None:
                    if inner.type == "function_definition":
                        self._emit_function(inner, scope=inner_scope, container_kind="class")
                    elif inner.type == "field_declaration":
                        self._emit_field(inner, scope=inner_scope)

    def _emit_field(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        # field_declaration may carry either a field_identifier (data member)
        # or a function_declarator (method declaration without body).
        decl = _first_child(node, "function_declarator")
        if decl is not None:
            name = _first_child_text(decl, "field_identifier")
            if name is None:
                name = _first_child_text(decl, "identifier")
            if name is None:
                return
            self.symbols.append(
                Symbol(
                    id=self._make_id(
                        [*list(scope), Descriptor(name=name, kind=DescriptorKind.METHOD)]
                    ),
                    kind="method",
                    language=LANG,
                    file=self.relative_path,
                    range=_node_range(node),
                    signature=f"{name}()",
                )
            )
            return
        name = _first_child_text(node, "field_identifier")
        if name is None:
            return
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), Descriptor(name=name, kind=DescriptorKind.TERM)]),
                kind="field",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
            )
        )

    def _emit_enum(
        self,
        node: tree_sitter.Node,
        *,
        scope: list[Descriptor],
    ) -> None:
        name = _first_child_text(node, "type_identifier")
        if name is None:
            return
        enum_desc = Descriptor(name=name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=self._make_id([*list(scope), enum_desc]),
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"cpp_kind": "enum"},
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
                                *list(scope),
                                enum_desc,
                                Descriptor(name=enum_name, kind=DescriptorKind.TERM),
                            ]
                        ),
                        kind="field",
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(child),
                        extra={"cpp_kind": "enumerator"},
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


_INNER_DECL_TYPES = frozenset(
    {
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "union_specifier",
        "enum_specifier",
        "field_declaration",
        "template_declaration",
    }
)


def _template_inner(node: tree_sitter.Node) -> tree_sitter.Node | None:
    for child in node.children:
        if child.type in _INNER_DECL_TYPES:
            return child
    return None


def _function_declarator_name(node: tree_sitter.Node) -> str | None:
    declarator = _first_child(node, "function_declarator")
    if declarator is None:
        for child in node.children:
            if child.type in {
                "pointer_declarator",
                "reference_declarator",
                "parenthesized_declarator",
            }:
                name = _function_declarator_name(child)
                if name is not None:
                    return name
        return None
    # function_declarator's first identifier is the function name.
    for child in declarator.children:
        if child.type in {"identifier", "field_identifier"}:
            return _node_text(child)
        if child.type == "qualified_identifier":
            # ``Foo::bar`` — take the rightmost component.
            return _qualified_name(child)
    return None


def _qualified_name(node: tree_sitter.Node) -> str | None:
    rightmost: str | None = None
    for child in node.children:
        if child.type in {"identifier", "field_identifier"}:
            rightmost = _node_text(child)
        elif child.type == "qualified_identifier":
            rightmost = _qualified_name(child) or rightmost
    return rightmost
