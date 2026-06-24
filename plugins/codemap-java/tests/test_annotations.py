"""Plan 3 Task 1: extract Java annotations on type and method declarations."""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_java import JavaIndexer

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str) -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return JavaIndexer().index_file(
        Path("src/Foo.java"),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp/p"),
            relative_path=PurePosixPath("src/Foo.java"),
            language="java",
        ),
    )


# ----- type-level annotations -----


def test_marker_annotation_on_class() -> None:
    r = _index(
        """
        @Service
        class Foo {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    names = {a.name for a in cls.annotations}
    assert "Service" in names


def test_annotation_with_string_argument() -> None:
    r = _index(
        """
        @RequestMapping("/api/order")
        class OrderController {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    ann = next(a for a in cls.annotations if a.name == "RequestMapping")
    assert ann.arguments == {"value": "/api/order"}


def test_annotation_with_named_arguments() -> None:
    r = _index(
        """
        @RequestMapping(value="/x", method="GET")
        class A {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    ann = next(a for a in cls.annotations if a.name == "RequestMapping")
    assert ann.arguments == {"value": "/x", "method": "GET"}


def test_multiple_class_annotations() -> None:
    r = _index(
        """
        @RestController
        @RequestMapping("/api")
        class A {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    names = {a.name for a in cls.annotations}
    assert {"RestController", "RequestMapping"} <= names


def test_no_annotation_yields_empty_list() -> None:
    r = _index("class A {}")
    cls = next(s for s in r.symbols if s.kind == "class")
    assert cls.annotations == []


# ----- method-level annotations -----


def test_method_post_mapping_annotation() -> None:
    r = _index(
        """
        class C {
            @PostMapping("/price")
            String calcPrice() { return ""; }
        }
        """
    )
    m = next(s for s in r.symbols if s.kind == "method")
    ann = next(a for a in m.annotations if a.name == "PostMapping")
    assert ann.arguments == {"value": "/price"}


def test_method_override_marker() -> None:
    r = _index(
        """
        class C {
            @Override
            String toString() { return ""; }
        }
        """
    )
    m = next(s for s in r.symbols if s.kind == "method")
    names = {a.name for a in m.annotations}
    assert "Override" in names


def test_method_multiple_annotations() -> None:
    r = _index(
        """
        class C {
            @Override
            @Deprecated
            String foo() { return ""; }
        }
        """
    )
    m = next(s for s in r.symbols if s.kind == "method")
    names = {a.name for a in m.annotations}
    assert {"Override", "Deprecated"} <= names


# ----- constructor + qualified annotation name -----


def test_constructor_annotation_recorded() -> None:
    r = _index(
        """
        class C {
            @Autowired
            C() {}
        }
        """
    )
    ctor = next(s for s in r.symbols if s.id.descriptors[-1].name == "<init>")
    assert any(a.name == "Autowired" for a in ctor.annotations)


def test_qualified_annotation_name_kept() -> None:
    r = _index(
        """
        @javax.inject.Inject
        class A {}
        """
    )
    cls = next(s for s in r.symbols if s.kind == "class")
    assert any(a.name == "javax.inject.Inject" for a in cls.annotations)
