"""Plan 2 Task 2 pre-req: capture field types + method parameter types.

The resolver needs these to follow ``foo.bar()`` from a field receiver to
the target class's method.
"""

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


# ----- field types -----


def test_field_type_recorded() -> None:
    r = _index(
        """
        class Foo {
            private CouponMapper couponMapper;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert fields[0].extra["type"] == "CouponMapper"


def test_field_primitive_type() -> None:
    r = _index(
        """
        class Foo {
            int counter;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert fields[0].extra["type"] == "int"


def test_field_qualified_type() -> None:
    r = _index(
        """
        class Foo {
            com.example.Bar bar;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert fields[0].extra["type"] == "com.example.Bar"


def test_field_generic_type_strips_args() -> None:
    r = _index(
        """
        import java.util.List;
        class Foo {
            List<String> names;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert fields[0].extra["type"] == "List"


def test_multiple_fields_in_one_decl_get_same_type() -> None:
    r = _index(
        """
        class Foo {
            int a, b, c;
        }
        """
    )
    fields = [s for s in r.symbols if s.kind == "field"]
    assert {f.id.descriptors[-1].name for f in fields} == {"a", "b", "c"}
    assert all(f.extra["type"] == "int" for f in fields)


# ----- method parameter types -----


def test_method_param_types_recorded() -> None:
    r = _index(
        """
        class Foo {
            void run(long userId, String name) {}
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    params = methods[0].extra["params"]
    assert params == [
        {"name": "userId", "type": "long"},
        {"name": "name", "type": "String"},
    ]


def test_method_no_params() -> None:
    r = _index("class Foo { void run() {} }")
    methods = [s for s in r.symbols if s.kind == "method"]
    assert methods[0].extra.get("params", []) == []


def test_method_param_generic_type_stripped() -> None:
    r = _index(
        """
        import java.util.List;
        class Foo {
            void run(List<String> items) {}
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert methods[0].extra["params"] == [{"name": "items", "type": "List"}]


def test_constructor_param_types_recorded() -> None:
    r = _index(
        """
        class Foo {
            Foo(CouponMapper m) {}
        }
        """
    )
    ctors = [s for s in r.symbols if s.kind == "method" and s.id.descriptors[-1].name == "<init>"]
    assert ctors[0].extra["params"] == [{"name": "m", "type": "CouponMapper"}]


def test_method_return_type_recorded() -> None:
    r = _index(
        """
        class Foo {
            CouponMapper getMapper() { return null; }
        }
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert methods[0].extra["return_type"] == "CouponMapper"


def test_constructor_has_no_return_type() -> None:
    r = _index("class Foo { Foo() {} }")
    ctors = [s for s in r.symbols if s.id.descriptors[-1].name == "<init>"]
    assert "return_type" not in ctors[0].extra
