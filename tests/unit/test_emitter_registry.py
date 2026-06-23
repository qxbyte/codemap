"""Plan 1 Task 3: Emitter protocol + EmitterRegistry."""

from __future__ import annotations

from pathlib import Path

from codemap.core.store import ReadOnlyStore
from codemap.emitters.base import EmitContext, Emitter, EmitResult
from codemap.emitters.registry import EmitterRegistry


class _Fake:
    name = "fake-emitter"
    version = "0.1.0"

    def emit(self, store: ReadOnlyStore, ctx: EmitContext) -> EmitResult:
        return EmitResult(files_written=["x.yml"], diagnostics=[])


def test_protocol_runtime_check() -> None:
    assert isinstance(_Fake(), Emitter)


def test_register_and_lookup() -> None:
    reg = EmitterRegistry()
    reg.register(_Fake())
    assert "fake-emitter" in reg.all()


def test_emit_context_defaults(tmp_path: Path) -> None:
    ctx = EmitContext(project_root=tmp_path, output_dir=tmp_path / ".ai-memory")
    assert ctx.config == {}
