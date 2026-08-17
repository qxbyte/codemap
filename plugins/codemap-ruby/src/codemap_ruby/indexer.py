"""Ruby indexer built on tree-sitter-ruby.

Tracks a class stack so nested modules / classes produce qualified
symbol IDs (``Outer#Inner#m()``). Top-level ``def`` is a function; ``def``
inside a class or module body is a method. ``singleton_method`` (``def
self.x``) is recorded as a method tagged ``extra.ruby_kind="singleton"``.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_ruby

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-ruby"
LANG = "ruby"

_RB_LANG = tree_sitter.Language(tree_sitter_ruby.language())


class RubyIndexer:
    name: ClassVar[str] = "ruby"
    version: ClassVar[str] = package_version("codemap-ruby")
    file_patterns: ClassVar[list[str]] = ["*.rb"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".rb"

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
                        code="RB002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_RB_LANG)
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
                    code="RB001",
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
        if kind == "class":
            self._visit_type(node, ruby_kind="class")
            return
        if kind == "module":
            self._visit_type(node, ruby_kind="module")
            return
        if kind == "method":
            self._visit_method(node, singleton=False)
            return
        if kind == "singleton_method":
            self._visit_method(node, singleton=True)
            return
        if kind == "assignment":
            self._visit_assignment(node)
        for child in node.children:
            self.visit(child)

    # ----------------------------------------------------- type-level

    def _visit_type(self, node: tree_sitter.Node, *, ruby_kind: str) -> None:
        name = _first_constant(node)
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
                extra={"ruby_kind": ruby_kind},
            )
        )
        self._type_stack.append(name)
        try:
            for child in node.children:
                if child.type == "body_statement":
                    for grand in child.children:
                        self.visit(grand)
        finally:
            self._type_stack.pop()

    # ----------------------------------------------------- methods

    def _visit_method(self, node: tree_sitter.Node, *, singleton: bool) -> None:
        name = _method_name(node)
        if name is None:
            return
        sym_kind: str = "method" if self._type_stack else "function"
        sid = self._make_id(name, kind=DescriptorKind.METHOD)
        extra: dict[str, str] = {}
        if singleton:
            extra["ruby_kind"] = "singleton"
        self.symbols.append(
            Symbol(
                id=sid,
                kind=sym_kind,  # type: ignore[arg-type]
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=f"def {name}",
                extra=extra,
            )
        )

    # ------------------------------------------------- constants / vars

    def _visit_assignment(self, node: tree_sitter.Node) -> None:
        # Capture top-level / inside-class assignments where the lhs is a
        # constant (uppercase Ruby identifier). Ignore everything else
        # (local variable assignments inside methods are not symbols).
        lhs = node.children[0] if node.children else None
        if lhs is None or lhs.type != "constant":
            return
        name = _node_text(lhs)
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


def _first_constant(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "constant":
            return _node_text(child)
        if child.type == "scope_resolution":
            # nested: `class A::B` — take the trailing constant.
            last = None
            for grand in child.children:
                if grand.type == "constant":
                    last = grand
            if last is not None:
                return _node_text(last)
    return None


def _method_name(node: tree_sitter.Node) -> str | None:
    """For ``def x`` returns ``x``; for ``def self.x`` returns ``x``."""
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child)
    return None
