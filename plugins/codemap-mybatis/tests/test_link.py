"""Tests for ``MyBatisLinkBridge`` — link sql_mapping ↔ java method."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from codemap_java import JavaIndexer
from codemap_mybatis import MyBatisIndexer
from codemap_mybatis.link import MyBatisLinkBridge

from codemap.core.models import Symbol
from codemap.indexers.base import IndexContext


class _StubStore:
    def __init__(self, symbols: list[Symbol]) -> None:
        self._symbols = symbols

    def iter_symbols(self):  # type: ignore[no-untyped-def]
        return iter(self._symbols)

    def get(self, sid):  # pragma: no cover
        return None

    def iter_edges(self):  # pragma: no cover
        return iter([])

    def callers(self, sid, *, depth=1):  # pragma: no cover
        return []

    def callees(self, sid, *, depth=1):  # pragma: no cover
        return []

    def search(self, query, *, limit=10):  # pragma: no cover
        return []

    def manifest(self):  # pragma: no cover
        raise NotImplementedError


def _index_java(source: str, *, rel: str) -> list[Symbol]:
    return list(
        JavaIndexer()
        .index_file(
            Path(f"/tmp/{rel}"),
            source.encode("utf-8"),
            IndexContext(
                project_root=Path("/tmp"),
                relative_path=PurePosixPath(rel),
                language="java",
            ),
        )
        .symbols
    )


def _index_xml(source: bytes, *, rel: str) -> list[Symbol]:
    return list(
        MyBatisIndexer()
        .index_file(
            Path(f"/tmp/{rel}"),
            source,
            IndexContext(
                project_root=Path("/tmp"),
                relative_path=PurePosixPath(rel),
                language="mybatis",
            ),
        )
        .symbols
    )


def _has_maps_to(edges, src_simple: str, tgt_simple: str) -> bool:
    return any(
        e.kind == "maps_to"
        and e.source.descriptors[-1].name == src_simple
        and e.target.descriptors[-1].name == tgt_simple
        for e in edges
    )


# ---------------------------------------------------------------------------


def test_bridge_metadata() -> None:
    b = MyBatisLinkBridge()
    assert b.name == "mybatis_link"


def test_maps_java_method_to_sql_mapping() -> None:
    java = _index_java(
        """
        package com.example;
        public interface CouponMapper {
            int selectByUser(long userId);
        }
        """,
        rel="src/com/example/CouponMapper.java",
    )
    xml = _index_xml(
        b"""<?xml version='1.0'?>
        <mapper namespace="com.example.CouponMapper">
            <select id="selectByUser" resultType="x">SELECT * FROM sf_coupon</select>
        </mapper>""",
        rel="src/mapper/CouponMapper.xml",
    )
    result = MyBatisLinkBridge().resolve(_StubStore(java + xml))
    assert _has_maps_to(result.edges, "selectByUser", "selectByUser")
    assert all(e.confidence == "medium" for e in result.edges if e.kind == "maps_to")


def test_no_match_when_namespace_unknown() -> None:
    """Mapper XML points at a namespace that isn't indexed → no edge."""
    xml = _index_xml(
        b"""<?xml version='1.0'?>
        <mapper namespace="com.example.NotIndexedMapper">
            <select id="x">SELECT * FROM t</select>
        </mapper>""",
        rel="src/mapper/x.xml",
    )
    result = MyBatisLinkBridge().resolve(_StubStore(xml))
    assert result.edges == []


def test_method_name_must_match_exactly() -> None:
    java = _index_java(
        """
        package com.example;
        public interface M {
            int findOne(long id);
        }
        """,
        rel="src/com/example/M.java",
    )
    xml = _index_xml(
        b"""<?xml version='1.0'?>
        <mapper namespace="com.example.M">
            <select id="findTwo">SELECT * FROM t</select>
        </mapper>""",
        rel="src/mapper/M.xml",
    )
    result = MyBatisLinkBridge().resolve(_StubStore(java + xml))
    assert result.edges == []
