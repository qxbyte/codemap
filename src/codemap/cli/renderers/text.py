"""Human-readable renderers built on rich."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def console(*, stderr: bool = False) -> Console:
    return Console(stderr=stderr)


def table(title: str, columns: list[str], rows: list[list[Any]]) -> Table:
    t = Table(title=title, show_lines=False, header_style="bold")
    for c in columns:
        t.add_column(c)
    for row in rows:
        t.add_row(*[str(x) for x in row])
    return t


__all__ = ["console", "table"]
