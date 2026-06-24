"""Plan 3 Task 2: Spring http_route metadata on handler methods.

Indexer combines the class-level ``@RequestMapping`` prefix with the
method-level verb mapping (``@GetMapping`` / ``@PostMapping`` / etc.) and
writes the resulting ``{"method", "path"}`` dict into the method symbol's
``extra["http_route"]``. The existing ``http_route`` bridge then mints a
route intermediate and produces ``routes_to`` edges in the bridge phase.
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


def _methods(r: IndexResult):  # type: ignore[no-untyped-def]
    return [s for s in r.symbols if s.kind == "method"]


# ----- combined class + method paths -----


def test_post_mapping_combines_with_class_prefix() -> None:
    r = _index(
        """
        @RestController
        @RequestMapping("/api/order")
        class OrderController {
            @PostMapping("/price")
            String calcPrice() { return ""; }
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"] == {"method": "POST", "path": "/api/order/price"}


def test_get_mapping_combines_with_class_prefix() -> None:
    r = _index(
        """
        @RequestMapping("/users")
        class UserController {
            @GetMapping("/{id}")
            String get(long id) { return ""; }
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"] == {"method": "GET", "path": "/users/{id}"}


def test_method_mapping_without_class_prefix() -> None:
    r = _index(
        """
        @RestController
        class C {
            @PutMapping("/x")
            void f() {}
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"] == {"method": "PUT", "path": "/x"}


def test_bare_request_mapping_on_method_defaults_to_get() -> None:
    r = _index(
        """
        @RequestMapping("/api")
        class C {
            @RequestMapping("/x")
            void f() {}
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"] == {"method": "GET", "path": "/api/x"}


def test_method_without_mapping_has_no_http_route() -> None:
    r = _index(
        """
        @RequestMapping("/api")
        class C {
            void helper() {}
        }
        """
    )
    m = _methods(r)[0]
    assert "http_route" not in m.extra


def test_no_class_no_method_mapping_no_route() -> None:
    r = _index(
        """
        class C {
            void f() {}
        }
        """
    )
    m = _methods(r)[0]
    assert "http_route" not in m.extra


def test_delete_and_patch_mappings() -> None:
    r = _index(
        """
        @RequestMapping("/x")
        class C {
            @DeleteMapping("/d") void d() {}
            @PatchMapping("/p")  void p() {}
        }
        """
    )
    ms = {m.id.descriptors[-1].name: m for m in _methods(r)}
    assert ms["d"].extra["http_route"] == {"method": "DELETE", "path": "/x/d"}
    assert ms["p"].extra["http_route"] == {"method": "PATCH", "path": "/x/p"}


def test_path_joining_handles_extra_slashes() -> None:
    r = _index(
        """
        @RequestMapping("/api/")
        class C {
            @GetMapping("/x")
            void f() {}
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"]["path"] == "/api/x"


def test_method_path_with_no_argument_uses_class_prefix() -> None:
    r = _index(
        """
        @RequestMapping("/api")
        class C {
            @GetMapping
            void f() {}
        }
        """
    )
    m = _methods(r)[0]
    assert m.extra["http_route"] == {"method": "GET", "path": "/api"}
