"""Reference indexer used to validate the end-to-end pipeline.

Files ending in ``.example`` are treated as a tiny pseudo-language:

* Each line starting with ``def NAME`` declares a function symbol named
  ``NAME`` at that line.
* Each line containing ``call NAME`` records a ``calls`` edge from the most
  recent ``def`` to ``NAME``.

The indexer is intentionally minimal — it exists so Sprint 0 can prove that
the storage, registry, and CLI layers compose end-to-end without depending on
any real-language parser. It is published through the ``codemap.indexers``
entry-point and registers on equal footing with third-party indexers.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from codemap.core.models import Diagnostic, Edge, IndexResult, Range, Symbol
from codemap.core.symbol import Descriptor, DescriptorKind, SymbolID
from codemap.indexers.base import IndexContext

LANG = "example"
SCHEME = "scip-example"


class ExampleLangIndexer:
    name: ClassVar[str] = "_example_lang"
    version: ClassVar[str] = "0.1.0"
    file_patterns: ClassVar[list[str]] = ["*.example"]
    languages: ClassVar[list[str]] = [LANG]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".example"

    def index_file(
        self,
        path: Path,
        source: bytes,
        ctx: IndexContext,
    ) -> IndexResult:
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            return IndexResult(
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        file=ctx.relative_path,
                        code="EXAMPLE001",
                        message=f"not valid UTF-8: {exc}",
                        producer=self.name,
                    )
                ]
            )

        symbols: list[Symbol] = []
        edges: list[Edge] = []
        diagnostics: list[Diagnostic] = []

        current_function: SymbolID | None = None
        current_range: Range | None = None

        for line_no, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("def "):
                name = stripped[4:].split()[0].rstrip("()")
                if not name:
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            file=ctx.relative_path,
                            range=Range(start_line=line_no, end_line=line_no),
                            code="EXAMPLE002",
                            message="empty def name",
                            producer=self.name,
                        )
                    )
                    continue
                sid = _make_symbol_id(ctx.relative_path, name)
                current_range = Range(start_line=line_no, end_line=line_no)
                symbols.append(
                    Symbol(
                        id=sid,
                        kind="function",
                        language=LANG,
                        file=ctx.relative_path,
                        range=current_range,
                        signature=f"def {name}()",
                    )
                )
                current_function = sid
                continue
            if "call " in stripped:
                target_name = stripped.split("call ", 1)[1].split()[0]
                if current_function is None:
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            file=ctx.relative_path,
                            range=Range(start_line=line_no, end_line=line_no),
                            code="EXAMPLE003",
                            message=f"'call {target_name}' outside any def",
                            producer=self.name,
                        )
                    )
                    continue
                target_id = _make_symbol_id(ctx.relative_path, target_name)
                edges.append(
                    Edge(
                        source=current_function,
                        target=target_id,
                        kind="calls",
                        location=Range(start_line=line_no, end_line=line_no),
                    )
                )

        return IndexResult(symbols=symbols, edges=edges, diagnostics=diagnostics)


def _make_symbol_id(_file: PurePosixPath, function_name: str) -> SymbolID:
    # The reference language uses a single global namespace so that cross-file
    # ``call`` references resolve to the same SymbolID. Real-world indexers
    # generally encode the file/module into the namespace.
    return SymbolID(
        scheme=SCHEME,
        descriptors=(Descriptor(name=function_name, kind=DescriptorKind.METHOD),),
    )


__all__ = ["LANG", "SCHEME", "ExampleLangIndexer"]
