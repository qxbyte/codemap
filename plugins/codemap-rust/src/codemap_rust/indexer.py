"""Rust indexer built on tree-sitter-rust.

Notable Rust-specific behaviour: ``impl_item`` blocks (both inherent and
trait impls) attach their inner functions to the impl'd type's namespace,
so ``impl User { fn login(&self) {} }`` and ``impl Greeter for User {
fn hello(&self) {} }`` both produce ``User#xxx().`` SymbolIDs. Methods
defined directly on a trait (``trait T { fn m(&self); }``) attach to the
trait the same way.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_rust

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap_rust._version import __version__

SCHEME = "scip-rust"
LANG = "rust"

_RUST_LANG = tree_sitter.Language(tree_sitter_rust.language())


class RustIndexer:
    name: ClassVar[str] = "rust"
    version: ClassVar[str] = __version__
    file_patterns: ClassVar[list[str]] = ["*.rs"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".rs"

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
                        code="RS002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_RUST_LANG)
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
                    code="RS001",
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
        if kind == "function_item":
            self._visit_function_item(node)
            return
        if kind == "function_signature_item" and self._type_stack:
            self._visit_function_signature_item(node)
            return
        if kind == "struct_item":
            self._visit_type_decl(node, rust_kind="struct")
            return
        if kind == "enum_item":
            self._visit_type_decl(node, rust_kind="enum")
            return
        if kind == "trait_item":
            self._visit_trait_item(node)
            return
        if kind == "impl_item":
            self._visit_impl_item(node)
            return
        if kind == "const_item":
            self._visit_const_or_static(node, rust_kind="const")
            return
        if kind == "static_item":
            self._visit_const_or_static(node, rust_kind="static")
            return
        for child in node.children:
            self.visit(child)

    # ---------------------------------------------------- functions

    def _visit_function_item(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
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
                signature=_fn_signature(node, name),
            )
        )

    def _visit_function_signature_item(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        sid = self._make_id(name, kind=DescriptorKind.METHOD)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=_fn_signature(node, name),
                extra={"rust_kind": "trait_method"},
            )
        )

    # ------------------------------------------------------ types

    def _visit_type_decl(self, node: tree_sitter.Node, *, rust_kind: str) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"rust_kind": rust_kind},
            )
        )

    def _visit_trait_item(self, node: tree_sitter.Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"rust_kind": "trait"},
            )
        )
        body = node.child_by_field_name("body")
        if body is None:
            return
        self._type_stack.append(name)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._type_stack.pop()

    def _visit_impl_item(self, node: tree_sitter.Node) -> None:
        owner = _impl_owner_type(node)
        body = node.child_by_field_name("body")
        if owner is None or body is None:
            # Walk anyway to capture function symbols at file scope.
            for child in node.children:
                self.visit(child)
            return
        self._type_stack.append(owner)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._type_stack.pop()

    # ----------------------------------------------- const / static

    def _visit_const_or_static(self, node: tree_sitter.Node, *, rust_kind: str) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = _node_text(name_node)
        if not name:
            return
        sid = self._make_id(name, kind=DescriptorKind.TERM)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="variable",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"rust_kind": rust_kind},
            )
        )

    # ----------------------------------------------------- helpers

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


def _fn_signature(node: tree_sitter.Node, name: str) -> str:
    params = node.child_by_field_name("parameters")
    params_text = _node_text(params) if params is not None else "()"
    return_type = node.child_by_field_name("return_type")
    rt_text = (" -> " + _node_text(return_type)) if return_type is not None else ""
    return f"fn {name}{params_text}{rt_text}"


def _impl_owner_type(impl_node: tree_sitter.Node) -> str | None:
    """Return the owning type of an impl block.

    For ``impl Foo { ... }`` returns ``"Foo"``. For
    ``impl Trait for Foo { ... }`` returns ``"Foo"`` (the receiver, not
    the trait).
    """
    # Field-named child ``type`` is the receiver of the impl (both inherent
    # and trait impls).
    type_node = impl_node.child_by_field_name("type")
    if type_node is not None:
        return _unwrap_type(type_node)
    # Fallback: walk children, take the last `type_identifier` before the
    # `declaration_list`.
    last: tree_sitter.Node | None = None
    for child in impl_node.children:
        if child.type == "declaration_list":
            break
        if child.type in {"type_identifier", "generic_type", "scoped_type_identifier"}:
            last = child
    if last is None:
        return None
    return _unwrap_type(last)


def _unwrap_type(node: tree_sitter.Node) -> str | None:
    if node.type == "type_identifier":
        return _node_text(node)
    if node.type == "generic_type":
        for c in node.children:
            if c.type == "type_identifier":
                return _node_text(c)
        return None
    if node.type == "scoped_type_identifier":
        for c in reversed(node.children):
            if c.type == "type_identifier":
                return _node_text(c)
        return None
    return None
