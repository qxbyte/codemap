"""SQL indexer built on tree-sitter-sql.

Only DDL statements (CREATE TABLE / VIEW / INDEX) produce symbols. The
table column list is walked to emit field symbols attached to the
parent table, so callers can answer "which table has column X" and the
http_route / asset bridges can cross-reference application code against
schema state.

Query statements (SELECT / INSERT / UPDATE / DELETE) are intentionally
ignored — they are not durable schema artefacts.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_sql

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext
from codemap.plugin_metadata import package_version

SCHEME = "scip-sql"
LANG = "sql"

_SQL_LANG = tree_sitter.Language(tree_sitter_sql.language())


class SqlIndexer:
    name: ClassVar[str] = "sql"
    version: ClassVar[str] = package_version("codemap-sql")
    file_patterns: ClassVar[list[str]] = ["*.sql", "*.ddl"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix in {".sql", ".ddl"}

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
                        code="SQL002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_SQL_LANG)
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
                    code="SQL001",
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

    def visit(self, node: tree_sitter.Node) -> None:
        kind = node.type
        if kind == "create_table":
            self._visit_create_table(node)
            return
        if kind == "create_view":
            self._visit_create_view(node)
            return
        if kind == "create_index":
            self._visit_create_index(node)
            return
        for child in node.children:
            self.visit(child)

    # -------------------------------------------------------- types

    def _visit_create_table(self, node: tree_sitter.Node) -> None:
        name = _object_name(node)
        if name is None:
            return
        sid = self._make_id([], name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"sql_kind": "table"},
            )
        )
        # Walk column_definitions for column names.
        for child in node.children:
            if child.type != "column_definitions":
                continue
            for sub in child.children:
                if sub.type == "column_definition":
                    self._emit_column(name, sub)

    def _emit_column(self, table_name: str, node: tree_sitter.Node) -> None:
        col_name = None
        for child in node.children:
            if child.type == "identifier":
                col_name = _node_text(child)
                break
        if not col_name:
            return
        sid = self._make_id([table_name], col_name, kind=DescriptorKind.TERM)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="field",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
            )
        )

    def _visit_create_view(self, node: tree_sitter.Node) -> None:
        name = _object_name(node)
        if name is None:
            return
        sid = self._make_id([], name, kind=DescriptorKind.TYPE)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"sql_kind": "view"},
            )
        )

    def _visit_create_index(self, node: tree_sitter.Node) -> None:
        # create_index > identifier (index name) is the first identifier.
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = _node_text(child)
                break
        if name is None:
            return
        sid = self._make_id([], name, kind=DescriptorKind.TERM)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="variable",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra={"sql_kind": "index"},
            )
        )

    # ---------------------------------------------------- helpers

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


def _object_name(node: tree_sitter.Node) -> str | None:
    """Pull a CREATE TABLE / VIEW target name from `object_reference`."""
    for child in node.children:
        if child.type != "object_reference":
            continue
        # Take the last identifier so schema-qualified `db.users` → "users".
        last = None
        for grand in child.children:
            if grand.type == "identifier":
                last = grand
        if last is not None:
            return _node_text(last)
    return None
