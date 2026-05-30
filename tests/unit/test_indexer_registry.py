"""Tests for the Indexer + Bridge registries and the reference example indexer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar

import pytest

from codemap.core.bridge.base import Bridge
from codemap.core.bridge.registry import BridgeCycleError, BridgeRegistry
from codemap.core.models import BridgeResult, IndexResult
from codemap.indexers._example_lang import ExampleLangIndexer
from codemap.indexers.base import IndexContext, Indexer
from codemap.indexers.registry import IndexerRegistry

# ---------------------------------------------------------------------------
# Built-in entry-point discovery
# ---------------------------------------------------------------------------


def test_example_indexer_is_discovered() -> None:
    reg = IndexerRegistry()
    by_name = reg.all()
    assert "_example_lang" in by_name
    assert isinstance(by_name["_example_lang"], Indexer)


def test_for_path_filters_by_supports() -> None:
    reg = IndexerRegistry()
    [ix] = list(reg.for_path(Path("foo.example")))
    assert ix.name == "_example_lang"
    assert list(reg.for_path(Path("foo.unknownext"))) == []


def test_manual_register_overrides() -> None:
    class DummyIndexer:
        name: ClassVar[str] = "_example_lang"
        version: ClassVar[str] = "9.9.9"
        file_patterns: ClassVar[list[str]] = ["*.example"]
        languages: ClassVar[list[str]] = ["example"]

        def supports(self, path: Path) -> bool:
            return True

        def index_file(
            self,
            path: Path,
            source: bytes,
            ctx: IndexContext,
        ) -> IndexResult:
            return IndexResult()

    reg = IndexerRegistry()
    reg.register(DummyIndexer())
    assert reg.all()["_example_lang"].version == "9.9.9"


# ---------------------------------------------------------------------------
# Example indexer behavior
# ---------------------------------------------------------------------------


def _index(source: str, *, path: str = "demo.example") -> IndexResult:
    indexer = ExampleLangIndexer()
    return indexer.index_file(
        Path(path),
        source.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath(path),
            language="example",
        ),
    )


def test_example_extracts_function_definitions() -> None:
    result = _index("def alpha\ndef beta\n")
    assert [s.signature for s in result.symbols] == ["def alpha()", "def beta()"]
    assert result.edges == []
    assert result.diagnostics == []


def test_example_extracts_call_edges() -> None:
    result = _index("def caller\n  call callee\ndef callee\n")
    names = [s.signature for s in result.symbols]
    assert names == ["def caller()", "def callee()"]
    assert len(result.edges) == 1
    e = result.edges[0]
    assert "caller" in str(e.source)
    assert "callee" in str(e.target)
    assert e.kind == "calls"


def test_example_warns_on_call_outside_def() -> None:
    result = _index("call dangling\n")
    assert result.symbols == []
    assert result.edges == []
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "EXAMPLE003"


def test_example_handles_non_utf8() -> None:
    indexer = ExampleLangIndexer()
    result = indexer.index_file(
        Path("bad.example"),
        b"\xff\xfe garbage",
        IndexContext(
            project_root=Path("/tmp/proj"),
            relative_path=PurePosixPath("bad.example"),
            language="example",
        ),
    )
    assert result.symbols == []
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "error"


def test_example_ignores_comments_and_blank_lines() -> None:
    result = _index("\n# a comment\ndef only\n")
    assert len(result.symbols) == 1


# ---------------------------------------------------------------------------
# Bridge registry
# ---------------------------------------------------------------------------


@dataclass
class _StubBridge:
    name: str = "stub"
    version: str = "0.1.0"
    requires: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.requires is None:
            self.requires = []

    def resolve(self, store: object) -> BridgeResult:
        return BridgeResult()


def test_bridge_topological_order_simple_chain() -> None:
    reg = BridgeRegistry()
    a = _StubBridge(name="a")
    b = _StubBridge(name="b", requires=["a"])
    c = _StubBridge(name="c", requires=["b"])
    reg.register(c)
    reg.register(b)
    reg.register(a)
    order = [br.name for br in reg.topological_order()]
    # The default reference bridge list may be empty initially; the order
    # should respect declared dependencies.
    assert order.index("a") < order.index("b") < order.index("c")


def test_bridge_topological_order_detects_cycle() -> None:
    reg = BridgeRegistry()
    a = _StubBridge(name="a", requires=["b"])
    b = _StubBridge(name="b", requires=["a"])
    reg.register(a)
    reg.register(b)
    with pytest.raises(BridgeCycleError):
        reg.topological_order()


def test_bridge_runtime_check() -> None:
    assert isinstance(_StubBridge(), Bridge)
