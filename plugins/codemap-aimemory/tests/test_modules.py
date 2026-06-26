"""Tests for the per-file module aggregator (P0-1 follow-up)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codemap_aimemory.modules import aggregate_modules, file_to_module_slug


@dataclass
class _Sym:
    id: str
    kind: str
    file: str
    language: str = ""


def _ids(*pairs: tuple[str, str]) -> dict[str, str]:
    return dict(pairs)


# ---------- file_to_module_slug ----------


def test_slug_strips_src_prefix_and_extension() -> None:
    assert file_to_module_slug("src/codemap/cli/commands/index.py") == "codemap-cli-commands-index"


def test_slug_strips_java_maven_layout() -> None:
    assert file_to_module_slug("src/main/java/com/demo/Svc.java") == "com-demo-Svc"


def test_slug_handles_no_prefix() -> None:
    assert file_to_module_slug("Makefile") == "Makefile"


def test_slug_handles_backslash_paths() -> None:
    assert file_to_module_slug("src\\codemap\\x.py") == "codemap-x"


# ---------- aggregate_modules ----------


def test_groups_fn_and_cls_by_file() -> None:
    symbols: list[Any] = [
        _Sym(id="s1", kind="function", file="src/a.py", language="python"),
        _Sym(id="s2", kind="class", file="src/a.py", language="python"),
        _Sym(id="s3", kind="function", file="src/b.py", language="python"),
    ]
    eids = _ids(("s1", "fn-one"), ("s2", "cls-A"), ("s3", "fn-two"))
    mods = aggregate_modules(symbols, eids)
    assert len(mods) == 2
    a = next(m for m in mods if m["path"] == "src/a.py")
    assert a["id"] == "mod-a"
    assert a["fn_count"] == 1
    assert a["cls_count"] == 1
    assert a["functions"] == ["fn-one"]
    assert a["classes"] == ["cls-A"]


def test_modules_sorted_by_path() -> None:
    symbols: list[Any] = [
        _Sym(id="s1", kind="function", file="src/z.py"),
        _Sym(id="s2", kind="function", file="src/a.py"),
        _Sym(id="s3", kind="function", file="src/m.py"),
    ]
    eids = _ids(("s1", "fn-z"), ("s2", "fn-a"), ("s3", "fn-m"))
    paths = [m["path"] for m in aggregate_modules(symbols, eids)]
    assert paths == ["src/a.py", "src/m.py", "src/z.py"]


def test_files_with_only_non_fn_cls_symbols_are_omitted() -> None:
    """Tables / files-only symbols belong to entities/tables.yml,
    not modules.yml. They mustn't surface as zero-symbol modules."""
    symbols: list[Any] = [
        _Sym(id="t1", kind="table", file="mappers/order.xml"),
        _Sym(id="s1", kind="function", file="src/a.py"),
    ]
    eids = _ids(("t1", "tbl-order"), ("s1", "fn-one"))
    mods = aggregate_modules(symbols, eids)
    assert [m["path"] for m in mods] == ["src/a.py"]


def test_unknown_symbol_ids_dropped() -> None:
    symbols: list[Any] = [
        _Sym(id="s1", kind="function", file="src/a.py"),
        _Sym(id="s2", kind="function", file="src/a.py"),
    ]
    eids = _ids(("s1", "fn-one"))  # s2 missing
    mods = aggregate_modules(symbols, eids)
    assert mods[0]["functions"] == ["fn-one"]
    assert mods[0]["fn_count"] == 1


def test_language_captured_per_module() -> None:
    symbols: list[Any] = [
        _Sym(id="s1", kind="function", file="src/Svc.java", language="java"),
        _Sym(id="s2", kind="function", file="web/App.vue", language="vue"),
    ]
    eids = _ids(("s1", "fn-svc"), ("s2", "fn-app"))
    mods = {m["path"]: m for m in aggregate_modules(symbols, eids)}
    assert mods["src/Svc.java"]["language"] == "java"
    assert mods["web/App.vue"]["language"] == "vue"


def test_functions_and_classes_within_module_sorted() -> None:
    symbols: list[Any] = [
        _Sym(id="s1", kind="function", file="src/a.py"),
        _Sym(id="s2", kind="function", file="src/a.py"),
        _Sym(id="s3", kind="function", file="src/a.py"),
    ]
    eids = _ids(("s1", "fn-z"), ("s2", "fn-a"), ("s3", "fn-m"))
    mod = aggregate_modules(symbols, eids)[0]
    assert mod["functions"] == ["fn-a", "fn-m", "fn-z"]
