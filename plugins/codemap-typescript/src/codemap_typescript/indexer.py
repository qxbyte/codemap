"""TypeScript indexer built on tree-sitter-typescript.

The indexer walks the tree-sitter parse tree once and emits
:class:`Symbol`, :class:`Edge`, and :class:`Diagnostic` objects through
the host CodeMap protocols. It does not parse, embed, or otherwise hold
on to any non-AST state — single-file by design, like the built-in
Python indexer.

The implementation purposefully covers a small, illustrative subset of
TypeScript syntax. The aim is to prove the plugin mechanism end to end,
not to ship a production-grade indexer in one shot. A real v0.2.0 would
add: interface kind support upstream, generic-parameter descriptors,
decorator capture, cross-file import resolution via a separate bridge.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_typescript

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-typescript"
LANG = "typescript"

_TS_LANG = tree_sitter.Language(tree_sitter_typescript.language_typescript())
_TSX_LANG = tree_sitter.Language(tree_sitter_typescript.language_tsx())


class TypeScriptIndexer:
    name: ClassVar[str] = "typescript"
    version: ClassVar[str] = package_version("codemap-typescript")
    file_patterns: ClassVar[list[str]] = ["*.ts", "*.tsx"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".ts", ".tsx"}

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
                        code="TS002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        lang = _TSX_LANG if path.suffix == ".tsx" else _TS_LANG
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source)
        if tree.root_node.has_error:
            # tree-sitter still produces a partial tree; surface the fact.
            return _walk_with_diagnostic(tree.root_node, ctx)
        return _walk(tree.root_node, ctx)


# ---------------------------------------------------------------------------
# AST walking
# ---------------------------------------------------------------------------


def _walk(root: tree_sitter.Node, ctx: IndexContext) -> IndexResult:
    visitor = _Visitor(ctx.relative_path)
    visitor.visit(root)
    return IndexResult(
        symbols=visitor.symbols,
        edges=visitor.edges,
        diagnostics=visitor.diagnostics,
    )


def _walk_with_diagnostic(root: tree_sitter.Node, ctx: IndexContext) -> IndexResult:
    """Walk a partially-parsed tree and tack on a syntax-error diagnostic."""
    result = _walk(root, ctx)
    result.diagnostics.append(
        Diagnostic(
            severity="warning",
            file=ctx.relative_path,
            range=Range(start_line=1, end_line=1),
            code="TS001",
            message="tree-sitter reported parse errors; symbols may be incomplete",
            producer="typescript",
        )
    )
    return result


class _Visitor:
    """Single-pass cursor walk over the tree-sitter parse tree."""

    def __init__(self, relative_path: PurePosixPath) -> None:
        self.relative_path = relative_path
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.diagnostics: list[Diagnostic] = []
        self._class_stack: list[str] = []

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "function_declaration":
            self._visit_function(node, is_method=False)
            return
        if kind == "class_declaration":
            self._visit_class(node)
            return
        if kind == "interface_declaration":
            self._visit_interface(node)
            return
        if kind == "method_definition":
            self._visit_function(node, is_method=True)
            return
        if kind == "lexical_declaration":
            self._visit_top_level_lexical(node)
        elif kind == "import_statement":
            self._visit_import(node)
        for child in node.children:
            self.visit(child)

    # ----------------------------------------------------- declarations

    def _visit_class(self, node: tree_sitter.Node) -> None:
        name = _name_child_text(node)
        if name is None:
            return
        sid = self._make_id(name, descriptor_kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
            )
        )
        self._class_stack.append(name)
        try:
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    self.visit(child)
        finally:
            self._class_stack.pop()

    def _visit_interface(self, node: tree_sitter.Node) -> None:
        name = _name_child_text(node)
        if name is None:
            return
        sid = self._make_id(name, descriptor_kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",  # design §3.3 has no `interface` kind yet
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"ts_kind": "interface"},
            )
        )
        # Interface bodies are signatures only; nothing to walk further.

    def _visit_function(self, node: tree_sitter.Node, *, is_method: bool) -> None:
        name = _name_child_text(node)
        if name is None:
            return
        sid = self._make_id(name, descriptor_kind=DescriptorKind.METHOD)
        kind: str = "method" if is_method or self._class_stack else "function"
        signature = _function_signature(node, name)
        self.symbols.append(
            Symbol(
                id=sid,
                kind=kind,  # type: ignore[arg-type]
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=signature,
            )
        )
        # Walk into the body so nested classes / functions are discovered.
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                self.visit(child)

    def _visit_top_level_lexical(self, node: tree_sitter.Node) -> None:
        """Only catch module-level `const`/`let` declarations (not inside fns)."""
        if self._class_stack:
            return  # class body's lexicals are handled via method_definition path
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                continue
            name = name_node.text.decode("utf-8") if name_node.text else ""
            if not name:
                continue
            sid = self._make_id(name, descriptor_kind=DescriptorKind.TERM)
            self.symbols.append(
                Symbol(
                    id=sid,
                    kind="variable",
                    language=LANG,
                    file=self.relative_path,
                    range=_node_range(child),
                )
            )

    def _visit_import(self, node: tree_sitter.Node) -> None:
        source_node = node.child_by_field_name("source")
        if source_node is None or source_node.text is None:
            return
        module = source_node.text.decode("utf-8").strip("\"'`")
        if not module:
            return
        # Imports at module top-level have no enclosing callable, so no edge —
        # mirroring the Python indexer's policy. ``_module_symbol_id`` is kept
        # for a future bridge that wants to act on the import target.
        _ = _module_symbol_id(module)

    # ---------------------------------------------------------- helpers

    def _make_id(self, name: str, *, descriptor_kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(
            Descriptor(name=cls, kind=DescriptorKind.TYPE) for cls in self._class_stack
        )
        descriptors.append(Descriptor(name=name, kind=descriptor_kind))
        return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _path_namespaces(path: PurePosixPath) -> list[Descriptor]:
    return [Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in path.parts]


def _module_symbol_id(spec: str) -> SymbolID:
    # `./foo`, `../bar`, `mylib` — keep the literal as the leaf.
    parts = [p for p in spec.split("/") if p and p != "."]
    descriptors = [Descriptor(name=p, kind=DescriptorKind.NAMESPACE) for p in parts[:-1]]
    descriptors.append(Descriptor(name=parts[-1] if parts else spec, kind=DescriptorKind.META))
    return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))


def _node_range(node: tree_sitter.Node) -> Range:
    start_row, start_col = node.start_point
    end_row, end_col = node.end_point
    return Range(
        start_line=start_row + 1,
        start_col=start_col,
        end_line=max(end_row + 1, start_row + 1),
        end_col=end_col,
    )


def _name_child_text(node: tree_sitter.Node) -> str | None:
    """Return the textual name field of a declaration node, if present."""
    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.text is None:
        return None
    text = name_node.text.decode("utf-8").strip()
    return text or None


def _function_signature(node: tree_sitter.Node, name: str) -> str:
    params = node.child_by_field_name("parameters")
    params_text = ""
    if params is not None and params.text is not None:
        params_text = params.text.decode("utf-8")
    prefix = "function" if node.type == "function_declaration" else ""
    return (f"{prefix} {name}{params_text}").strip()
