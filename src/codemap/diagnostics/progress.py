"""Thin wrapper over ``rich.progress`` used by the indexing pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

T = TypeVar("T")


@contextmanager
def progress_bar(
    description: str,
    total: int | None = None,
    *,
    enabled: bool = True,
    console: Console | None = None,
) -> Iterator[Progress]:
    """Yield a configured ``rich.Progress`` (or a silent no-op when disabled)."""
    if not enabled:
        yield _SilentProgress()  # type: ignore[misc]
        return
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console or Console(stderr=True),
        transient=True,
    ) as p:
        p.add_task(description, total=total)
        yield p


class _SilentProgress:
    """Stand-in that swallows update calls when ``--no-progress`` is set."""

    def __enter__(self) -> _SilentProgress:
        return self

    def __exit__(self, *exc: object) -> None:  # pragma: no cover
        return None

    def add_task(self, *_a: object, **_kw: object) -> int:  # pragma: no cover
        return 0

    def update(self, *_a: object, **_kw: object) -> None:  # pragma: no cover
        return None

    def advance(self, *_a: object, **_kw: object) -> None:  # pragma: no cover
        return None

    def stop(self) -> None:  # pragma: no cover
        return None


__all__ = ["progress_bar"]
