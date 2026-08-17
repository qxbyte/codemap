"""Vue SFC indexer.

Strategy
========

``.vue`` files mix three languages — HTML-like ``<template>``,
JS / TS in ``<script>``, and CSS / SCSS / Less in ``<style>``. Since
``tree-sitter-vue`` is not available on PyPI, this plugin:

1. Uses :mod:`codemap_vue.sfc` to locate every top-level ``<script>``
   block in the file and read its ``lang=`` attribute.
2. Dispatches the block's bytes to the matching tree-sitter grammar
   (``tree-sitter-javascript`` for JS / JSX, ``tree-sitter-typescript``
   for TS / TSX). The TypeScript grammar is an optional dependency —
   ``.vue`` files that declare ``lang="ts"`` without it installed
   produce a diagnostic, not a crash.
3. Walks the inner parse tree, collecting top-level functions, classes
   (with methods), and module-level ``const`` / ``let`` / ``var``
   declarations. Symbol line numbers are translated from script-local
   to file-global coordinates so ``codemap get`` jumps to the right
   line in the ``.vue`` source.

``<template>`` and ``<style>`` are intentionally ignored — they are
covered by neither tree-sitter-javascript nor tree-sitter-typescript,
and their template-only constructs are best served by a dedicated
``codemap-html`` plugin if such coverage is ever needed.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_javascript

from codemap.core.models import Diagnostic, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version
from codemap_vue.sfc import ScriptBlock, extract_script_blocks

SCHEME = "scip-vue"
LANG = "vue"

_JS_LANG = tree_sitter.Language(tree_sitter_javascript.language())

try:
    import tree_sitter_typescript as _ts_module

    _TS_LANG: tree_sitter.Language | None = tree_sitter.Language(_ts_module.language_typescript())
    _TSX_LANG: tree_sitter.Language | None = tree_sitter.Language(_ts_module.language_tsx())
except ImportError:  # pragma: no cover - exercised in integration only
    _TS_LANG = None
    _TSX_LANG = None


class VueIndexer:
    name: ClassVar[str] = "vue"
    version: ClassVar[str] = package_version("codemap-vue")
    file_patterns: ClassVar[list[str]] = ["*.vue"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".vue"

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
                        code="VUE002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )

        blocks = extract_script_blocks(source)
        if not blocks:
            return IndexResult()

        symbols: list[Symbol] = []
        diagnostics: list[Diagnostic] = []

        for block in blocks:
            lang_obj = _lang_for(block.lang)
            if lang_obj is None:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        file=ctx.relative_path,
                        range=Range(
                            start_line=block.content_start_line, end_line=block.content_start_line
                        ),
                        code="VUE003",
                        message=(
                            f'<script lang="{block.lang}"> requires tree-sitter-typescript; '
                            f"install with: pip install codemap-vue[typescript]"
                        ),
                        producer=self.name,
                    )
                )
                continue

            parser = tree_sitter.Parser(lang_obj)
            tree = parser.parse(block.content)
            if tree.root_node.has_error:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        file=ctx.relative_path,
                        range=Range(
                            start_line=block.content_start_line, end_line=block.content_start_line
                        ),
                        code="VUE001",
                        message="tree-sitter reported parse errors inside <script>; symbols may be incomplete",
                        producer=self.name,
                    )
                )

            visitor = _ScriptVisitor(ctx.relative_path, block)
            visitor.visit(tree.root_node)
            symbols.extend(visitor.symbols)

        return IndexResult(symbols=symbols, diagnostics=diagnostics)


def _lang_for(script_lang: str) -> tree_sitter.Language | None:
    if script_lang in {"js", "jsx"}:
        return _JS_LANG
    if script_lang == "ts":
        return _TS_LANG
    if script_lang == "tsx":
        return _TSX_LANG
    return _JS_LANG


# ---------------------------------------------------------------------------
# AST walking (mirrors codemap-typescript / codemap-javascript)
# ---------------------------------------------------------------------------


class _ScriptVisitor:
    """Walks one ``<script>`` block's AST, translating positions."""

    def __init__(self, relative_path: PurePosixPath, block: ScriptBlock) -> None:
        self.relative_path = relative_path
        self.block = block
        self.symbols: list[Symbol] = []
        self._class_stack: list[str] = []
        # When inside a function body, the topmost ``http_calls`` collector
        # accumulates axios/fetch invocations to attach to the enclosing
        # function symbol on exit. Pairs (symbol, calls list).
        self._fn_stack: list[tuple[Symbol, list[dict[str, str]]]] = []

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "function_declaration":
            self._visit_function(node, is_method=False)
            return
        if kind == "class_declaration":
            self._visit_class(node)
            return
        if kind == "method_definition":
            self._visit_function(node, is_method=True)
            return
        if kind in {"lexical_declaration", "variable_declaration"}:
            self._visit_top_level_declaration(node)
        if kind == "call_expression":
            self._maybe_record_http_call(node)
        for child in node.children:
            self.visit(child)

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

    def _visit_function(self, node: tree_sitter.Node, *, is_method: bool) -> None:
        name = _name_child_text(node)
        if name is None:
            return
        sid = self._make_id(name, descriptor_kind=DescriptorKind.METHOD)
        kind: str = "method" if is_method or self._class_stack else "function"
        signature = _function_signature(node, name)
        symbol = Symbol(
            id=sid,
            kind=kind,  # type: ignore[arg-type]
            language=LANG,
            file=self.relative_path,
            range=self._node_range(node),
            signature=signature,
            extra={"vue_block_lang": self.block.lang},
        )
        self.symbols.append(symbol)
        body = node.child_by_field_name("body")
        if body is None:
            return
        http_calls: list[dict[str, str]] = []
        self._fn_stack.append((symbol, http_calls))
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._fn_stack.pop()
        if http_calls:
            symbol.extra["http_calls"] = http_calls

    def _visit_top_level_declaration(self, node: tree_sitter.Node) -> None:
        if self._class_stack:
            return
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
                    range=self._node_range(child),
                    extra={"vue_block_lang": self.block.lang},
                )
            )

    def _maybe_record_http_call(self, node: tree_sitter.Node) -> None:
        """If ``node`` is an axios / fetch call inside a function we know about,
        append a record to the enclosing function's http_calls list."""
        if not self._fn_stack:
            return
        record = _classify_http_call(node)
        if record is not None:
            self._fn_stack[-1][1].append(record)

    def _make_id(self, name: str, *, descriptor_kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(
            Descriptor(name=cls, kind=DescriptorKind.TYPE) for cls in self._class_stack
        )
        descriptors.append(Descriptor(name=name, kind=descriptor_kind))
        return SymbolID(scheme=SCHEME, descriptors=tuple(descriptors))

    def _node_range(self, node: tree_sitter.Node) -> Range:
        """Convert script-local row to file-global row by adding block offset."""
        start_row, start_col = node.start_point
        end_row, end_col = node.end_point
        # The block's content_start_line is 1-based and is the line where
        # the content starts; node start_row is 0-based within the block.
        offset = self.block.content_start_line - 1
        return Range(
            start_line=start_row + 1 + offset,
            start_col=start_col,
            end_line=max(end_row + 1 + offset, start_row + 1 + offset),
            end_col=end_col,
        )


# ---------------------------------------------------------------------------
# Pure helpers (shared shape with sibling indexers)
# ---------------------------------------------------------------------------


def _path_namespaces(path: PurePosixPath) -> list[Descriptor]:
    return [Descriptor(name=part, kind=DescriptorKind.NAMESPACE) for part in path.parts]


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
    prefix = "function" if node.type == "function_declaration" else ""
    return (f"{prefix} {name}{params_text}").strip()


# ---------------------------------------------------------------------------
# HTTP-call classification (Plan 4 Task 1)
# ---------------------------------------------------------------------------

_HTTP_VERBS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _classify_http_call(node: tree_sitter.Node) -> dict[str, str] | None:
    """Recognize ``axios.<verb>(url, ...)`` / ``this.$axios.<verb>(...)`` /
    ``fetch(url, ...)`` and return ``{method, url, confidence}`` or ``None``
    for any other call. URL confidence is ``medium`` for plain string
    literals, ``low`` for templates / concatenations / non-string args."""
    fn = node.child_by_field_name("function")
    args = node.child_by_field_name("arguments")
    if fn is None or args is None:
        return None

    verb: str | None = None
    if fn.type == "identifier" and _decoded(fn) == "fetch":
        verb = "GET"
    elif fn.type == "member_expression":
        prop = fn.child_by_field_name("property")
        obj = fn.child_by_field_name("object")
        if prop is None or obj is None:
            return None
        prop_name = _decoded(prop).lower()
        if prop_name not in _HTTP_VERBS:
            return None
        obj_text = _decoded(obj)
        if "axios" not in obj_text and "$http" not in obj_text:
            return None
        verb = prop_name.upper()

    if verb is None:
        return None

    first_arg = _first_named_child(args)
    if first_arg is None:
        return None
    url, confidence = _extract_url(first_arg)
    if url is None:
        return None
    return {"method": verb, "url": url, "confidence": confidence}


def _first_named_child(args_node: tree_sitter.Node) -> tree_sitter.Node | None:
    for child in args_node.children:
        if child.type not in {"(", ")", ","}:
            return child
    return None


def _extract_url(arg: tree_sitter.Node) -> tuple[str | None, str]:
    text = _decoded(arg)
    if arg.type == "string":
        return text.strip("'\"`"), "medium"
    if arg.type == "template_string":
        return text.strip("`"), "low"
    if arg.type in {"binary_expression"}:
        # Best-effort: take the leftmost string literal if any.
        for child in arg.children:
            if child.type == "string":
                return _decoded(child).strip("'\""), "low"
        return None, "low"
    return None, "low"


def _decoded(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""
