"""Go indexer built on tree-sitter-go.

Notable Go-specific behaviour: ``method_declaration`` carries a receiver
parameter list before the method name. The indexer pulls the receiver's
type out and attaches the method as ``<TypeName>#methodName()`` so a
later query like ``callers 'scip-go . . . main.go/User#Login().'`` can
find every cross-receiver caller via the cross-module bridge.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_go

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-go"
LANG = "go"

_GO_LANG = tree_sitter.Language(tree_sitter_go.language())


class GoIndexer:
    name: ClassVar[str] = "go"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.go"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".go"

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
                        code="GO002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_GO_LANG)
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
                    code="GO001",
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
        self._package: str = ""

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "package_clause":
            self._set_package(node)
            return
        if kind == "function_declaration":
            self._visit_function(node)
            return
        if kind == "method_declaration":
            self._visit_method(node)
            return
        if kind == "type_declaration":
            for spec in node.children:
                if spec.type == "type_spec":
                    self._visit_type_spec(spec)
            return
        if kind == "const_declaration":
            self._visit_const_or_var(node, go_kind="const")
            return
        if kind == "var_declaration":
            self._visit_const_or_var(node, go_kind="var")
            return
        for child in node.children:
            self.visit(child)

    # ------------------------------------------------------------ pkg

    def _set_package(self, node: tree_sitter.Node) -> None:
        for child in node.children:
            if child.type == "package_identifier":
                self._package = _node_text(child)
                return

    # ------------------------------------------------------- functions

    def _visit_function(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        sid = self._make_id([], name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="function",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=_function_signature(node, name),
                extra={"package": self._package} if self._package else {},
            )
        )

    def _visit_method(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        receiver_type = _extract_receiver_type(node)
        if receiver_type is None:
            # Methods without resolvable receivers are dropped — they would
            # otherwise alias against unrelated top-level functions.
            return
        sid = self._make_id([receiver_type], name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=_function_signature(node, name),
                extra={
                    "package": self._package,
                    "receiver_type": receiver_type,
                },
            )
        )

    # ----------------------------------------------------------- types

    def _visit_type_spec(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        body = node.child_by_field_name("type")
        if body is not None and body.type == "struct_type":
            go_kind = "struct"
        elif body is not None and body.type == "interface_type":
            go_kind = "interface"
        else:
            go_kind = "type"
        sid = self._make_id([], name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"package": self._package, "go_kind": go_kind},
            )
        )

    # ---------------------------------------------------- vars / consts

    def _visit_const_or_var(self, node: tree_sitter.Node, *, go_kind: str) -> None:
        for spec in node.children:
            if spec.type not in {"const_spec", "var_spec"}:
                continue
            for child in spec.children:
                if child.type != "identifier":
                    continue
                name = _node_text(child)
                if not name:
                    continue
                sid = self._make_id([], name, kind=DescriptorKind.TERM)
                self.symbols.append(
                    Symbol(
                        id=sid,
                        kind="variable",
                        language=LANG,
                        file=self.relative_path,
                        range=_node_range(spec),
                        extra={"package": self._package, "go_kind": go_kind}
                        if self._package
                        else {"go_kind": go_kind},
                    )
                )

    # --------------------------------------------------------- helpers

    def _make_id(
        self,
        type_chain: list[str],
        name: str,
        *,
        kind: DescriptorKind,
    ) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(Descriptor(name=t, kind=DescriptorKind.TYPE) for t in type_chain)
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


def _function_signature(node: tree_sitter.Node, name: str) -> str:
    params = node.child_by_field_name("parameters")
    params_text = _node_text(params) if params is not None else "()"
    result = node.child_by_field_name("result")
    result_text = (" " + _node_text(result)) if result is not None else ""
    return f"func {name}{params_text}{result_text}"


def _extract_receiver_type(method_node: tree_sitter.Node) -> str | None:
    """For ``func (u User) M()`` and ``func (u *User) M()`` return ``User``."""
    receiver = method_node.child_by_field_name("receiver")
    if receiver is None:
        # Some versions of the grammar don't expose `receiver` by name —
        # fall back to the first parameter_list before the method name.
        for child in method_node.children:
            if child.type == "parameter_list":
                receiver = child
                break
    if receiver is None:
        return None
    for param in receiver.children:
        if param.type != "parameter_declaration":
            continue
        type_node = param.child_by_field_name("type")
        if type_node is None:
            # Walk children to find the type
            for c in param.children:
                if c.type in {"type_identifier", "pointer_type", "qualified_type"}:
                    type_node = c
                    break
        if type_node is None:
            continue
        return _unwrap_type(type_node)
    return None


def _unwrap_type(node: tree_sitter.Node) -> str | None:
    if node.type == "type_identifier":
        return _node_text(node)
    if node.type == "pointer_type":
        for c in node.children:
            if c.type == "type_identifier":
                return _node_text(c)
            if c.type == "qualified_type":
                return _unwrap_type(c)
        return None
    if node.type == "qualified_type":
        for c in node.children:
            if c.type == "type_identifier":
                return _node_text(c)
        return None
    return None
