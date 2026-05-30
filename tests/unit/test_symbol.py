"""Tests for `codemap.core.symbol.SymbolID` — SCIP encoding round-trip,
parse error paths, escape handling, and Pydantic v2 integration.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel, ValidationError

from codemap.core.symbol import (
    Descriptor,
    DescriptorKind,
    SymbolID,
    SymbolParseError,
)

# ---------------------------------------------------------------------------
# Round-trip table for representative real-world symbols
# ---------------------------------------------------------------------------

ROUND_TRIP_CASES = [
    # Python source symbol with method descriptor
    "scip-python pypi . . src/auth/login.py/LoginHandler#verify().",
    # Java source symbol with maven coordinates
    "scip-java maven com.foo/user-service 1.0.0 com/foo/UserMapper#findUsers().",
    # Java symbol with local manager (no published coordinates)
    "scip-java local . . src/main/java/com/foo/UserMapper.java/UserMapper#findUsers().",
    # MyBatis-style custom scheme (asset → interface alias)
    "scip-mybatis local . . src/main/resources/mapper/UserMapper.xml/com/foo/UserMapper#findUsers.",
    # HTTP route intermediate symbol (URL path must be backtick-escaped because
    # it contains slashes, which are descriptor separators).
    "scip-route local . . api/v1#GET#`/api/user/list`.",
    # Vue component symbol with namespace + method
    "scip-vue local . . src/SearchButton.vue/setup#handleClick().",
    # Vue template anchor (term descriptor)
    "scip-vue local . . src/SearchButton.vue/template#search-button.",
    # TypeScript with npm coordinates
    "scip-typescript npm @org/pkg 1.0.0 src/api/user.ts/fetchUsers().",
    # Go without manager
    "scip-go . . . pkg/auth/login.go/Verify().",
    # Rust with cargo coordinates
    "scip-rust cargo crate 1.0.0 src/auth/login.rs/Login#verify().",
    # Method with disambiguator (overloaded)
    "scip-java maven com.foo/x 1.0.0 com/foo/X#m(int).",
    # Method with parameter descriptor following
    "scip-java maven com.foo/x 1.0.0 com/foo/X#m().(arg)",
    # Type parameter
    "scip-java maven com.foo/x 1.0.0 com/foo/X#[T]m().",
    # Bare term symbol (e.g., a constant)
    "scip-python pypi . . src/constants.py/MAX_RETRIES.",
    # Meta descriptor
    "scip-rust cargo crate 1.0.0 src/lib.rs/foo:",
    # Deep namespace nesting
    "scip-python pypi . . src/a/b/c/d/e/f.py/Foo#bar().",
]


@pytest.mark.parametrize("sym", ROUND_TRIP_CASES)
def test_round_trip(sym: str) -> None:
    assert SymbolID.parse(sym).to_string() == sym


def test_parse_returns_immutable_dataclass() -> None:
    sid = SymbolID.parse("scip-python pypi . . foo/bar.")
    with pytest.raises(FrozenInstanceError):
        sid.scheme = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Descriptor parsing detail
# ---------------------------------------------------------------------------


def test_namespace_chain() -> None:
    sid = SymbolID.parse("scip-python . . . a/b/c/Klass#")
    kinds = [d.kind for d in sid.descriptors]
    assert kinds == [
        DescriptorKind.NAMESPACE,
        DescriptorKind.NAMESPACE,
        DescriptorKind.NAMESPACE,
        DescriptorKind.TYPE,
    ]
    assert [d.name for d in sid.descriptors] == ["a", "b", "c", "Klass"]


def test_method_without_disambiguator() -> None:
    sid = SymbolID.parse("scip-python . . . m().")
    assert sid.descriptors == (Descriptor(name="m", kind=DescriptorKind.METHOD),)


def test_method_with_disambiguator() -> None:
    sid = SymbolID.parse("scip-java . . . m(int).")
    (d,) = sid.descriptors
    assert d.kind is DescriptorKind.METHOD
    assert d.name == "m"
    assert d.disambiguator == "int"


def test_type_parameter_and_parameter() -> None:
    sid = SymbolID.parse("scip-java . . . Klass#[T]m().(x)")
    kinds = [d.kind for d in sid.descriptors]
    assert kinds == [
        DescriptorKind.TYPE,
        DescriptorKind.TYPE_PARAMETER,
        DescriptorKind.METHOD,
        DescriptorKind.PARAMETER,
    ]


def test_meta_descriptor() -> None:
    sid = SymbolID.parse("scip-rust . . . lib/foo:")
    assert sid.descriptors[-1] == Descriptor(name="foo", kind=DescriptorKind.META)


def test_trailing_dot_recovery_as_term() -> None:
    # Greedy parsing absorbs the final '.' into the name; the parser must
    # give it back as the TERM suffix.
    sid = SymbolID.parse("scip-python . . . foo.")
    assert sid.descriptors == (Descriptor(name="foo", kind=DescriptorKind.TERM),)


def test_dotted_namespace_preserved() -> None:
    # `login.py/` — '.' is a valid identifier char, '/' is the suffix.
    sid = SymbolID.parse("scip-python . . . src/login.py/Handler#")
    assert sid.descriptors[1].name == "login.py"
    assert sid.descriptors[1].kind is DescriptorKind.NAMESPACE


# ---------------------------------------------------------------------------
# Escape handling
# ---------------------------------------------------------------------------


def test_escaped_name_with_spaces() -> None:
    sid = SymbolID.parse("scip-rust . . . `name with spaces`#")
    assert sid.descriptors == (Descriptor(name="name with spaces", kind=DescriptorKind.TYPE),)


def test_escaped_name_with_backtick() -> None:
    # Escape rule: '``' inside an escaped string is a literal backtick.
    sid = SymbolID.parse("scip-rust . . . `weird``name`#")
    assert sid.descriptors[0].name == "weird`name"


def test_escaped_name_round_trip() -> None:
    original = "scip-rust . . . `name with /slash`#"
    assert SymbolID.parse(original).to_string() == original


def test_encode_name_auto_escapes_special_chars() -> None:
    sid = SymbolID(
        scheme="scip-rust",
        descriptors=(Descriptor(name="weird name", kind=DescriptorKind.TYPE),),
    )
    assert sid.to_string() == "scip-rust . . . `weird name`#"


def test_encode_name_auto_escapes_backtick() -> None:
    sid = SymbolID(
        scheme="scip-rust",
        descriptors=(Descriptor(name="ti`ck", kind=DescriptorKind.TYPE),),
    )
    assert sid.to_string() == "scip-rust . . . `ti``ck`#"


def test_encode_empty_name() -> None:
    sid = SymbolID(
        scheme="scip-x",
        descriptors=(Descriptor(name="", kind=DescriptorKind.TYPE),),
    )
    assert sid.to_string() == "scip-x . . . ``#"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        "scip-python",  # only one field
        "scip-python . . .",  # only header, no body
        "scip-python . . . ",  # header but empty body (parses to 0 descriptors)
        "scip-python . . . foo",  # name with no suffix
        "scip-python . . . [foo",  # unterminated type parameter
        "scip-python . . . (foo",  # unterminated parameter
        "scip-python . . . foo(",  # method without ')'
        "scip-python . . . foo()",  # method ')' without '.'
        "scip-python . . . `unterminated",  # unterminated escape
        "scip-python . . . foo@",  # unknown suffix
    ],
)
def test_parse_errors(bad: str) -> None:
    with pytest.raises(SymbolParseError):
        SymbolID.parse(bad)


def test_parse_rejects_non_string() -> None:
    with pytest.raises(SymbolParseError):
        SymbolID.parse(123)  # type: ignore[arg-type]


def test_disambiguator_not_allowed_on_non_method() -> None:
    with pytest.raises(ValueError, match="disambiguator"):
        Descriptor(name="x", kind=DescriptorKind.TYPE, disambiguator="y")


# ---------------------------------------------------------------------------
# Pydantic v2 integration
# ---------------------------------------------------------------------------


class _Container(BaseModel):
    sym: SymbolID


def test_pydantic_accepts_string() -> None:
    obj = _Container.model_validate({"sym": "scip-python . . . foo()."})
    assert isinstance(obj.sym, SymbolID)
    assert obj.sym.descriptors[0].kind is DescriptorKind.METHOD


def test_pydantic_accepts_symbol_instance() -> None:
    sid = SymbolID.parse("scip-python . . . foo().")
    obj = _Container.model_validate({"sym": sid})
    assert obj.sym is sid or obj.sym == sid


def test_pydantic_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        _Container.model_validate({"sym": "not a valid symbol"})


def test_pydantic_serializes_as_string() -> None:
    obj = _Container(sym=SymbolID.parse("scip-python . . . foo()."))
    dumped = obj.model_dump()
    assert dumped == {"sym": "scip-python . . . foo()."}


def test_pydantic_round_trip_through_json() -> None:
    src = "scip-python . . . src/m.py/Foo#bar()."
    obj = _Container.model_validate({"sym": src})
    raw = obj.model_dump_json()
    rebuilt = _Container.model_validate_json(raw)
    assert rebuilt.sym.to_string() == src


# ---------------------------------------------------------------------------
# Hashing / equality
# ---------------------------------------------------------------------------


def test_symbol_is_hashable() -> None:
    a = SymbolID.parse("scip-python . . . foo().")
    b = SymbolID.parse("scip-python . . . foo().")
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1  # set deduplicates equal values


def test_different_schemes_are_not_equal() -> None:
    a = SymbolID.parse("scip-python . . . foo().")
    b = SymbolID.parse("scip-java . . . foo().")
    assert a != b
