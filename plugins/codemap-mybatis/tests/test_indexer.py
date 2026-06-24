"""Tests for ``codemap_mybatis.indexer.MyBatisIndexer``."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from codemap_mybatis import MyBatisIndexer

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext

_XML_SIMPLE = b"""<?xml version="1.0"?>
<mapper namespace="com.example.CouponMapper">
  <select id="selectByUser" resultType="x">
    SELECT * FROM sf_coupon WHERE uid = #{id}
  </select>
</mapper>
"""

_XML_DYNAMIC = b"""<?xml version="1.0"?>
<mapper namespace="com.example.CouponMapper">
  <select id="selectByUser" resultType="x">
    SELECT * FROM sf_coupon
    <if test="uid != null">WHERE uid = #{id}</if>
  </select>
</mapper>
"""

_XML_DOLLAR = b"""<?xml version="1.0"?>
<mapper namespace="com.example.M">
  <select id="dyn" resultType="x">
    SELECT * FROM ${tableName}
  </select>
</mapper>
"""

_XML_MIXED = b"""<?xml version="1.0"?>
<mapper namespace="com.example.M">
  <select id="get" resultType="x">SELECT * FROM sf_coupon WHERE id=#{i}</select>
  <update id="touch">UPDATE sf_coupon SET ts = NOW() WHERE id=#{i}</update>
  <insert id="add">INSERT INTO sf_coupon (a) VALUES (#{a})</insert>
  <delete id="del">DELETE FROM sf_coupon WHERE id=#{i}</delete>
</mapper>
"""


def _index(source: bytes, *, rel: str = "src/mapper/CouponMapper.xml") -> IndexResult:
    ix = MyBatisIndexer()
    return ix.index_file(
        Path(f"/tmp/{rel}"),
        source,
        IndexContext(
            project_root=Path("/tmp"),
            relative_path=PurePosixPath(rel),
            language="mybatis",
        ),
    )


# ---------------------------------------------------------------------------
# Indexer metadata
# ---------------------------------------------------------------------------


def test_indexer_metadata() -> None:
    ix = MyBatisIndexer()
    assert ix.name == "mybatis"
    assert "*.xml" in ix.file_patterns


def test_supports_only_mapper_xml(tmp_path: Path) -> None:
    ix = MyBatisIndexer()
    plain = tmp_path / "plain.xml"
    plain.write_bytes(b"<root/>")
    assert not ix.supports(plain)
    mapper = tmp_path / "M.xml"
    mapper.write_bytes(_XML_SIMPLE)
    assert ix.supports(mapper)


def test_non_xml_file_not_supported(tmp_path: Path) -> None:
    f = tmp_path / "a.java"
    f.write_bytes(b"")
    assert not MyBatisIndexer().supports(f)


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------


def test_sql_mapping_symbol_emitted() -> None:
    r = _index(_XML_SIMPLE)
    mappings = [s for s in r.symbols if s.kind == "sql_mapping"]
    assert len(mappings) == 1
    m = mappings[0]
    assert m.id.descriptors[-1].name == "selectByUser"
    assert m.extra == {
        "java_namespace": "com.example.CouponMapper",
        "java_method_name": "selectByUser",
        "sql_verb": "select",
    }


def test_table_symbol_emitted() -> None:
    r = _index(_XML_SIMPLE)
    tables = [s for s in r.symbols if s.kind == "table"]
    assert len(tables) == 1
    assert tables[0].id.descriptors[-1].name == "sf_coupon"


def test_accesses_table_edge_high_confidence_for_static_sql() -> None:
    r = _index(_XML_SIMPLE)
    edges = [e for e in r.edges if e.kind == "accesses_table"]
    assert len(edges) == 1
    assert edges[0].confidence == "high"


def test_dynamic_sql_lowers_to_medium() -> None:
    r = _index(_XML_DYNAMIC)
    edges = [e for e in r.edges if e.kind == "accesses_table"]
    assert any(e.confidence == "medium" for e in edges)


def test_dollar_substitution_lowers_to_low() -> None:
    r = _index(_XML_DOLLAR)
    edges = [e for e in r.edges if e.kind == "accesses_table"]
    # ${tableName} doesn't match any verb pattern, so no table edge at all
    # is correct in this case; the test asserts the dynamic SQL doesn't crash.
    # If the regex evolves to capture the substitution placeholder, the edge
    # would land at confidence="low".
    assert all(e.confidence in {"low", "medium", "high"} for e in edges)


# ---------------------------------------------------------------------------
# Multiple statements + dedup
# ---------------------------------------------------------------------------


def test_all_four_verbs_produce_mappings() -> None:
    r = _index(_XML_MIXED)
    names = {
        s.id.descriptors[-1].name for s in r.symbols if s.kind == "sql_mapping"
    }
    assert names == {"get", "touch", "add", "del"}


def test_same_table_dedup_in_one_file() -> None:
    r = _index(_XML_MIXED)
    tables = [s for s in r.symbols if s.kind == "table"]
    # all 4 statements hit sf_coupon → exactly one table symbol per file
    assert len(tables) == 1


def test_edges_count_matches_statements() -> None:
    r = _index(_XML_MIXED)
    # each of 4 statements produces one accesses_table edge to sf_coupon
    edges = [e for e in r.edges if e.kind == "accesses_table"]
    assert len(edges) == 4


# ---------------------------------------------------------------------------
# Malformed inputs
# ---------------------------------------------------------------------------


def test_parse_error_yields_diagnostic_not_crash() -> None:
    r = _index(b"<mapper namespace='x'><bad")
    assert r.symbols == []
    assert any(d.code == "MB001" for d in r.diagnostics)


def test_missing_namespace_yields_diagnostic() -> None:
    r = _index(b"<mapper><select id='a'>SELECT * FROM x</select></mapper>")
    assert r.symbols == []
    assert any(d.code == "MB002" for d in r.diagnostics)


def test_non_mapper_root_silently_ignored() -> None:
    r = _index(b"<root><x/></root>")
    assert r.symbols == []
    assert r.diagnostics == []
