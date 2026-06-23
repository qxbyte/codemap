"""Java indexer built on tree-sitter-java.

Covers class / interface / enum / record / method / constructor / field
declarations. Package declarations are honoured as a namespace prefix
under the file path. Nested types track a class stack to produce the
correct ``Cls#Inner#m()`` chain.

The indexer is single-file by design; cross-file ``extends`` / ``implements``
and call-graph resolution lives in :class:`codemap.core.bridge.java_calls
.JavaCallResolverBridge`. To enable that resolver, the indexer attaches three
metadata keys to ``Symbol.extra`` (ADR-0013):

* top-level type symbols carry ``imports`` (list[str], fully qualified)
* top-level type symbols carry ``supertypes`` (list of
  ``{"name": str, "relation": "extends"|"implements"}``)
* method / constructor symbols carry ``pending_calls`` — a list of raw
  invocation records ``{"receiver", "name", "arity", "line", "col"}`` for
  the bridge to FQN-resolve.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

import tree_sitter
import tree_sitter_java

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

SCHEME = "scip-java"
LANG = "java"

_JAVA_LANG = tree_sitter.Language(tree_sitter_java.language())

_TYPE_DECLS = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)


class JavaIndexer:
    name: ClassVar[str] = "java"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.java"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".java"

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
                        code="JAVA002",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )
        parser = tree_sitter.Parser(_JAVA_LANG)
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
                    code="JAVA001",
                    message="tree-sitter reported parse errors; symbols may be incomplete",
                    producer=self.name,
                )
            )
        return IndexResult(
            symbols=visitor.symbols,
            edges=visitor.edges,
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------


class _Visitor:
    def __init__(self, relative_path: PurePosixPath) -> None:
        self.relative_path = relative_path
        self.symbols: list[Symbol] = []
        self.edges: list[Edge] = []
        self.diagnostics: list[Diagnostic] = []
        self._class_stack: list[str] = []
        self._package: str = ""
        self._file_imports: list[str] = []

    def visit(self, node: tree_sitter.Node) -> None:
        if node.type == "package_declaration":
            self._package = _node_text(node.children[1]) if node.child_count > 1 else ""
            return
        if node.type == "import_declaration":
            imp = _parse_import(node)
            if imp:
                self._file_imports.append(imp)
            return
        if node.type in _TYPE_DECLS:
            self._visit_type(node)
            return
        if node.type == "method_declaration" and self._class_stack:
            self._visit_method(node, is_constructor=False)
            return
        if node.type == "constructor_declaration" and self._class_stack:
            self._visit_method(node, is_constructor=True)
            return
        if node.type == "field_declaration" and self._class_stack:
            self._visit_field(node)
            return
        for child in node.children:
            self.visit(child)

    # ------------------------------------------------------------- types

    def _visit_type(self, node: tree_sitter.Node) -> None:
        name = _name_child(node)
        if name is None:
            return
        java_kind = node.type.removesuffix("_declaration")
        is_top_level = not self._class_stack
        sid = self._make_id(name, kind=DescriptorKind.TYPE)
        extra: dict[str, object] = {}
        if self._package or java_kind != "class":
            extra["java_kind"] = java_kind
            extra["package"] = self._package
        if is_top_level:
            extra["imports"] = list(self._file_imports)
            extra["supertypes"] = _parse_supertypes(node)
        self.symbols.append(
            Symbol(
                id=sid,
                kind="class",  # Symbol schema has no separate interface/enum kind
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                extra=extra,
            )
        )
        body = node.child_by_field_name("body")
        if body is None:
            return
        self._class_stack.append(name)
        try:
            for child in body.children:
                self.visit(child)
        finally:
            self._class_stack.pop()

    # ----------------------------------------------------------- members

    def _visit_method(self, node: tree_sitter.Node, *, is_constructor: bool) -> None:
        name = _name_child(node)
        if name is None:
            return
        if is_constructor:
            display = "<init>"
            sid = self._make_id(display, kind=DescriptorKind.METHOD)
        else:
            display = name
            sid = self._make_id(name, kind=DescriptorKind.METHOD)
        signature = _method_signature(node, name, is_constructor=is_constructor)
        body = node.child_by_field_name("body")
        pending_calls = _collect_invocations(body) if body is not None else []
        params = _parse_formal_parameters(node.child_by_field_name("parameters"))
        extra: dict[str, object] = {"params": params}
        if not is_constructor:
            ret = node.child_by_field_name("type")
            if ret is not None:
                extra["return_type"] = _strip_generics(_node_text(ret))
        if pending_calls:
            extra["pending_calls"] = pending_calls
        self.symbols.append(
            Symbol(
                id=sid,
                kind="method",
                language=LANG,
                file=self.relative_path,
                range=_node_range(node),
                signature=signature,
                extra=extra,
            )
        )

    def _visit_field(self, node: tree_sitter.Node) -> None:
        type_node = node.child_by_field_name("type")
        type_str = _strip_generics(_node_text(type_node)) if type_node is not None else ""
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            name = _node_text(name_node)
            if not name:
                continue
            sid = self._make_id(name, kind=DescriptorKind.TERM)
            extra: dict[str, object] = {}
            if type_str:
                extra["type"] = type_str
            self.symbols.append(
                Symbol(
                    id=sid,
                    kind="field",
                    language=LANG,
                    file=self.relative_path,
                    range=_node_range(child),
                    extra=extra,
                )
            )

    # ----------------------------------------------------------- helpers

    def _make_id(self, name: str, *, kind: DescriptorKind) -> SymbolID:
        descriptors = list(_path_namespaces(self.relative_path))
        descriptors.extend(
            Descriptor(name=cls, kind=DescriptorKind.TYPE) for cls in self._class_stack
        )
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


def _name_child(node: tree_sitter.Node) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.text is None:
        return None
    text = _node_text(name_node).strip()
    return text or None


def _method_signature(
    node: tree_sitter.Node,
    name: str,
    *,
    is_constructor: bool,
) -> str:
    params = node.child_by_field_name("parameters")
    params_text = _node_text(params) if params is not None else "()"
    if is_constructor:
        return f"{name}{params_text}"
    return_type = node.child_by_field_name("type")
    rt_text = _node_text(return_type) + " " if return_type is not None else ""
    return f"{rt_text}{name}{params_text}"


# ---------------------------------------------------------------------------
# Metadata extractors for the JavaCallResolverBridge (ADR-0013)
# ---------------------------------------------------------------------------


def _parse_import(node: tree_sitter.Node) -> str:
    """Return the imported FQN. ``import static x.y.Z.m;`` → ``x.y.Z.m``;
    ``import java.util.*;`` → ``java.util.*``. Empty string on malformed
    input (returned to the caller, who drops empties)."""
    parts: list[str] = []
    saw_asterisk = False
    for child in node.children:
        ttype = child.type
        if ttype in {"import", "static", ";"}:
            continue
        if ttype == "asterisk":
            saw_asterisk = True
            continue
        if ttype in {"identifier", "scoped_identifier"}:
            parts.append(_node_text(child))
    if not parts:
        return ""
    path = ".".join(parts)
    return f"{path}.*" if saw_asterisk else path


def _parse_supertypes(type_node: tree_sitter.Node) -> list[dict[str, str]]:
    """Extract ``extends`` / ``implements`` relations off a type declaration.

    Handles ``class X extends A``, ``class X implements I, J``,
    ``class X extends A implements I``, and ``interface I extends J, K``.
    Generic type arguments (``Box<String>``) are stripped — bridge resolves
    by raw name, not parameterized type.
    """
    out: list[dict[str, str]] = []
    for child in type_node.children:
        ttype = child.type
        # `class` declarations: superclass / super_interfaces fields.
        if ttype == "superclass":
            out.extend({"name": name, "relation": "extends"} for name in _supertype_names(child))
        elif ttype == "super_interfaces":
            out.extend(
                {"name": name, "relation": "implements"} for name in _supertype_names(child)
            )
        # `interface` declarations: extends_interfaces.
        elif ttype == "extends_interfaces":
            out.extend({"name": name, "relation": "extends"} for name in _supertype_names(child))
    return out


def _supertype_names(container: tree_sitter.Node) -> list[str]:
    out: list[str] = []
    for child in container.children:
        ttype = child.type
        if ttype in {"type_identifier", "scoped_type_identifier"}:
            out.append(_node_text(child))
        elif ttype == "generic_type":
            # take the head type, drop ``<...>``
            head = child.child(0)
            if head is not None and head.type in {
                "type_identifier",
                "scoped_type_identifier",
            }:
                out.append(_node_text(head))
        elif ttype == "type_list":
            out.extend(_supertype_names(child))
    return out


def _collect_invocations(body: tree_sitter.Node) -> list[dict[str, object]]:
    """Walk ``body`` collecting every ``method_invocation`` node as a raw
    record. The bridge does FQN resolution; here we only capture the syntactic
    shape (receiver text, name, arity, location)."""
    records: list[dict[str, object]] = []

    def walk(node: tree_sitter.Node) -> None:
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            obj_node = node.child_by_field_name("object")
            args_node = node.child_by_field_name("arguments")
            if name_node is not None:
                receiver = _receiver_text(obj_node)
                name = _node_text(name_node)
                arity = _argument_arity(args_node)
                sr, sc = node.start_point
                records.append(
                    {
                        "receiver": receiver,
                        "name": name,
                        "arity": arity,
                        "line": sr + 1,
                        "col": sc,
                    }
                )
        for child in node.children:
            walk(child)

    walk(body)
    return records


def _receiver_text(obj: tree_sitter.Node | None) -> str:
    """Best-effort textual receiver. Empty for unqualified calls; the inner
    method's name for chained calls (``foo.bar().baz()`` → ``"bar"`` is the
    receiver of ``baz``)."""
    if obj is None:
        return ""
    ttype = obj.type
    if ttype in {"identifier", "scoped_identifier", "this", "super"}:
        return _node_text(obj)
    if ttype == "field_access":
        field = obj.child_by_field_name("field")
        return _node_text(field) if field is not None else ""
    if ttype == "method_invocation":
        inner = obj.child_by_field_name("name")
        return _node_text(inner) if inner is not None else ""
    return ""


def _argument_arity(args: tree_sitter.Node | None) -> int:
    if args is None:
        return 0
    # named_child_count skips punctuation tokens (`(`, `)`, `,`).
    return int(args.named_child_count)


def _parse_formal_parameters(node: tree_sitter.Node | None) -> list[dict[str, str]]:
    """Return ``[{"name": str, "type": str}]`` for each formal parameter.

    Generic type arguments are stripped (``List<String>`` → ``List``) so the
    FQN resolver can match by raw type name.
    """
    if node is None:
        return []
    out: list[dict[str, str]] = []
    for child in node.children:
        if child.type not in {"formal_parameter", "spread_parameter"}:
            continue
        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if name_node is None or type_node is None:
            # Spread parameters wrap the actual variable_declarator differently.
            for sub in child.children:
                if sub.type == "variable_declarator" and name_node is None:
                    name_node = sub.child_by_field_name("name")
        if name_node is None or type_node is None:
            continue
        out.append(
            {
                "name": _node_text(name_node),
                "type": _strip_generics(_node_text(type_node)),
            }
        )
    return out


def _strip_generics(t: str) -> str:
    """``Box<String, Integer>`` → ``Box``; arrays / primitives untouched."""
    t = t.strip()
    if "<" in t:
        return t.split("<", 1)[0].rstrip()
    return t
