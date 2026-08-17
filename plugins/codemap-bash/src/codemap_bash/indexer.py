"""Bash indexer built on tree-sitter-bash.

Only script-level symbols are emitted: function definitions, top-level
variable assignments, and top-level ``readonly`` / ``declare`` /
``export`` / ``local`` declaration commands. Variables defined inside a
function body are intentionally not surfaced — they are private state,
not a stable interface.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_bash

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-bash"
LANG = "bash"

_BASH_LANG = tree_sitter.Language(tree_sitter_bash.language())
_DECLARATION_KEYWORDS = frozenset({"readonly", "declare", "export", "local", "typeset"})


class BashIndexer:
    name: ClassVar[str] = "bash"
    version: ClassVar[str] = package_version("codemap-bash")
    file_patterns: ClassVar[list[str]] = ["*.sh", "*.bash", "*.bats"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        if path.suffix in {".sh", ".bash", ".bats"}:
            return True
        # Extensionless files with a bash shebang are also accepted.
        if path.suffix == "" and path.is_file():
            try:
                with path.open("rb") as f:
                    head = f.read(64)
                return _looks_like_bash_shebang(head)
            except OSError:
                return False
        return False

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
                        code="SH002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_BASH_LANG)
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
                    code="SH001",
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
        # We only walk the top-level statement list — function bodies are
        # opaque from the symbol-table perspective.
        for child in root.children:
            self._visit_top_level(child)

    def _visit_top_level(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "function_definition":
            self._emit_function(node)
            return
        if kind == "variable_assignment":
            self._emit_variable(node, bash_kind=None)
            return
        if kind == "declaration_command":
            self._emit_declaration(node)

    def _emit_function(self, node: tree_sitter.Node) -> None:
        name = _function_name(node)
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
                signature=f"{name}()",
            )
        )

    def _emit_variable(
        self,
        node: tree_sitter.Node,
        *,
        bash_kind: str | None,
    ) -> None:
        name = _variable_name(node)
        if name is None:
            return
        sid = self._make_id(name, kind=DescriptorKind.TERM)
        extra: dict[str, str] = {}
        if bash_kind is not None:
            extra["bash_kind"] = bash_kind
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

    def _emit_declaration(self, node: tree_sitter.Node) -> None:
        keyword: str | None = None
        for child in node.children:
            if child.type in _DECLARATION_KEYWORDS:
                keyword = child.type
                break
        for child in node.children:
            if child.type == "variable_assignment":
                self._emit_variable(child, bash_kind=keyword)

    def _make_id(self, name: str, *, kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
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


def _function_name(node: tree_sitter.Node) -> str | None:
    """``function greet() { ... }`` and ``helper() { ... }`` both expose the
    function name as a ``word`` child (sitting either after the optional
    ``function`` keyword or as the first content child).
    """
    for child in node.children:
        if child.type == "word":
            return _node_text(child)
    return None


def _variable_name(node: tree_sitter.Node) -> str | None:
    """For ``variable_assignment``: the ``variable_name`` child."""
    for child in node.children:
        if child.type == "variable_name":
            return _node_text(child)
    return None


_BASH_SHEBANGS = (b"#!/bin/bash", b"#!/usr/bin/env bash", b"#!/bin/sh", b"#!/usr/bin/env sh")


def _looks_like_bash_shebang(head: bytes) -> bool:
    return any(head.startswith(sb) for sb in _BASH_SHEBANGS)
