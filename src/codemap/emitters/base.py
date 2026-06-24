"""Emitter protocol — transforms the deterministic index into an external
output format (e.g. the four-layer memory model's ``.ai-memory/`` L1).

Emitters run after all indexers and bridges. They read a
:class:`codemap.core.store.ReadOnlyStore` and write files themselves; the
orchestrator decides when to invoke them. Registered via the
``codemap.emitters`` entry-point group on equal standing with indexers and
bridges (ADR-004, ADR-L001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from codemap.core.models import Diagnostic
from codemap.core.store import ReadOnlyStore

__all__ = ["EmitContext", "EmitResult", "Emitter"]


@dataclass(frozen=True, slots=True)
class EmitContext:
    project_root: Path
    output_dir: Path
    config: dict[str, object] = field(default_factory=dict)


class EmitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files_written: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


@runtime_checkable
class Emitter(Protocol):
    name: ClassVar[str]
    version: ClassVar[str]

    def emit(self, store: ReadOnlyStore, ctx: EmitContext) -> EmitResult: ...
