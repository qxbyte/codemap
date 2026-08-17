"""JSP (.jsp / .jspx / .tag / .tagx) indexer.

Strategy
========

JSP files are HTML-shaped containers with embedded Java in
``<%! ... %>`` (declarations) and ``<% ... %>`` (scriptlets), plus
``<%@ page import="..." %>`` directives. We scan the file once for
those constructs (:mod:`codemap_jsp.sfc`), then:

* Parse each ``<%! ... %>`` block's Java with ``tree-sitter-java`` and
  emit method / field / class symbols at the page level (these are the
  generated servlet's instance members and are the only Java symbols
  worth surfacing as a stable interface).
* Skip scriptlet bodies (`<% ... %>`) for symbol extraction — every
  statement in there is per-request local state, not a stable
  interface.
* Emit ``<form action="...">`` and ``<a href="...">`` URLs as
  ``http_client_calls`` (consumed by the host's ``http_route`` bridge
  to link the JSP page to its server controller).
* Treat each ``<%@ page import="..." %>`` as a hint of dependency on
  the cited Java type; recorded for future cross-asset bridging.

``<template>``-style tags, JSTL (`<c:if>`, `<c:forEach>`), and EL
(`${expr}`) are ignored — they have no symbol value here.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_java

from codemap.core.models import Diagnostic, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap_jsp._version import __version__
from codemap_jsp.sfc import JspDeclaration, JspExtract, extract

SCHEME = "scip-jsp"
LANG = "jsp"

_JAVA_LANG = tree_sitter.Language(tree_sitter_java.language())

# Server-side JSP page is conceptually a class; the canonical name we
# use as the enclosing type for its declared methods/fields is the file
# basename (the JSP servlet generator does the same).
_JSP_HTTP_CLIENT_EXTRA_KEY = "http_client_calls"


class JspIndexer:
    name: ClassVar[str] = "jsp"
    version: ClassVar[str] = __version__
    file_patterns: ClassVar[list[str]] = ["*.jsp", "*.jspx", "*.tag", "*.tagx"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".jsp", ".jspx", ".tag", ".tagx"}

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
                        code="JSP002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )

        ext = extract(source)
        page_symbol, page_kind_sids = _emit_page_symbol(ctx.relative_path, source, ext)
        symbols: list[Symbol] = [page_symbol]
        diagnostics: list[Diagnostic] = []

        # Parse declaration blocks for member symbols.
        for block in ext.declarations:
            block_symbols, block_diags = _index_declaration(
                ctx.relative_path, block, page_kind_sids
            )
            symbols.extend(block_symbols)
            diagnostics.extend(block_diags)

        return IndexResult(symbols=symbols, diagnostics=diagnostics)


def _emit_page_symbol(
    relative_path: PurePosixPath,
    source: bytes,
    ext: JspExtract,
) -> tuple[Symbol, list[Descriptor]]:
    """Emit the page-level pseudo-class symbol.

    Returns ``(page_symbol, page_type_descriptors)`` where the
    descriptors are reused when generating IDs for member symbols.
    """
    page_name = _page_type_name(relative_path)
    descriptors = [
        *_path_namespaces(relative_path),
        Descriptor(name=page_name, kind=DescriptorKind.TYPE),
    ]
    page_id = SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))

    extra: dict[str, object] = {
        "jsp_imports": [{"fqcn": i.fqcn, "line": i.line} for i in ext.imports],
        "jsp_includes": [{"path": i.path, "line": i.line} for i in ext.includes],
    }
    client_calls: list[dict[str, object]] = [
        {"method": fa.method, "url": fa.url, "line": fa.line} for fa in ext.form_actions
    ]
    client_calls.extend({"method": "GET", "url": link.url, "line": link.line} for link in ext.links)
    if client_calls:
        extra[_JSP_HTTP_CLIENT_EXTRA_KEY] = client_calls

    # Page range = full file
    total_lines = source.count(b"\n") + 1
    page_symbol = Symbol(
        id=page_id,
        kind="class",  # canonical "page = pseudo-class" mapping
        language=LANG,
        file=relative_path,
        range=Range(start_line=1, end_line=total_lines),
        extra=extra,
    )
    return page_symbol, descriptors


def _index_declaration(
    relative_path: PurePosixPath,
    block: JspDeclaration,
    page_type_descriptors: list[Descriptor],
) -> tuple[list[Symbol], list[Diagnostic]]:
    """Parse the Java member declarations in a ``<%! ... %>`` block.

    JSP declaration blocks are conceptually class-body content of the
    generated servlet, but tree-sitter-java's top-level grammar treats
    a bare ``private int x = 0;`` as a ``local_variable_declaration``
    rather than a ``field_declaration``. To get the right node kinds,
    we wrap the block in a synthetic ``class _S { ... }`` frame and
    walk inside that wrapper. The synthetic class itself contributes
    one extra line at the top, which we subtract from every emitted
    symbol's line number.
    """
    parser = tree_sitter.Parser(_JAVA_LANG)
    wrapped = b"class _S {\n" + block.content + b"\n}"
    tree = parser.parse(wrapped)
    diagnostics: list[Diagnostic] = []
    if tree.root_node.has_error:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                file=relative_path,
                range=Range(start_line=block.content_start_line, end_line=block.content_start_line),
                code="JSP001",
                message="tree-sitter reported parse errors inside <%! ... %>; symbols may be incomplete",
                producer=LANG,
            )
        )

    # The wrapper class contributes one extra line ("class _S {") above
    # the real content. Walk into the wrapper's body so we see field /
    # method / nested class declarations as Java grammar nodes.
    visitor = _DeclarationVisitor(
        relative_path=relative_path,
        # block_offset_line - 1 maps "row 0 in inner tree" to the first
        # actual content line of the JSP file. The wrapper's "class _S {"
        # is on row 0 of the parsed tree so its content begins on row 1,
        # which corresponds to block.content_start_line. Net offset: -1.
        block_offset_line=block.content_start_line - 1 - 1,
        page_type_descriptors=page_type_descriptors,
        synthetic_wrapper="_S",
    )
    visitor.visit(tree.root_node)
    return visitor.symbols, diagnostics


# ---------------------------------------------------------------------------
# Java AST walking inside <%! ... %>
# ---------------------------------------------------------------------------


class _DeclarationVisitor:
    """Walk one <%! ... %> block's Java AST and emit member symbols."""

    def __init__(
        self,
        relative_path: PurePosixPath,
        block_offset_line: int,
        page_type_descriptors: list[Descriptor],
        synthetic_wrapper: str | None = None,
    ) -> None:
        self.relative_path = relative_path
        self.offset = block_offset_line
        self.page_type_descriptors = page_type_descriptors
        # When a synthetic ``class _S { ... }`` is used to coerce
        # tree-sitter-java into emitting field_declaration nodes, we
        # filter the wrapper itself out of the symbol stream.
        self._synthetic_wrapper = synthetic_wrapper
        self.symbols: list[Symbol] = []
        self._class_stack: list[str] = []

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "method_declaration":
            self._visit_method(node)
            return
        if kind == "field_declaration":
            self._visit_field(node)
            return
        if kind == "class_declaration":
            name = _name_child_text(node)
            if name == self._synthetic_wrapper:
                # Walk into the wrapper's body but do not emit a symbol.
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        self.visit(child)
                return
            self._visit_class(node)
            return
        for child in node.children:
            self.visit(child)

    def _visit_method(self, node: tree_sitter.Node) -> None:
        name = _name_child_text(node)
        if name is None:
            return
        sid = self._make_id(name, descriptor_kind=DescriptorKind.METHOD)
        signature = _function_signature(node, name)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=self._node_range(node),
                signature=signature,
            )
        )

    def _visit_field(self, node: tree_sitter.Node) -> None:
        # field_declaration: type + variable_declarator[+]
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None or name_node.text is None:
                continue
            name = name_node.text.decode("utf-8")
            if not name:
                continue
            sid = self._make_id(name, descriptor_kind=DescriptorKind.TERM)
            self.symbols.append(
                Symbol(
                    id=sid,
                    kind="variable",
                    language=LANG,
                    file=self.relative_path,
                    range=self._node_range(child),
                )
            )

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
                range=self._node_range(node),
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

    def _make_id(self, name: str, *, descriptor_kind: DescriptorKind) -> SymbolID:
        descriptors = list(self.page_type_descriptors)
        descriptors.extend(
            Descriptor(name=cls, kind=DescriptorKind.TYPE) for cls in self._class_stack
        )
        descriptors.append(Descriptor(name=name, kind=descriptor_kind))
        return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))

    def _node_range(self, node: tree_sitter.Node) -> Range:
        start_row, start_col = node.start_point
        end_row, end_col = node.end_point
        return Range(
            start_line=start_row + 1 + self.offset,
            start_col=start_col,
            end_line=max(end_row + 1 + self.offset, start_row + 1 + self.offset),
            end_col=end_col,
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _path_namespaces(path: PurePosixPath) -> list[Descriptor]:
    return [Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in path.parts]


def _page_type_name(path: PurePosixPath) -> str:
    """Map ``foo/bar/UserList.jsp`` → ``UserList``."""
    stem = path.stem
    return stem or path.name


def _name_child_text(node: tree_sitter.Node) -> str | None:
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
    return f"{name}{params_text}".strip()
