"""SymbolID — SCIP-compatible cross-language symbol identifier.

This is the foundational data type for the entire system (ADR-001). A SymbolID
is a string-encoded handle that uniquely identifies a symbol across languages,
file types, and assets. The encoding follows the SCIP Symbol grammar so that
CodeMap can interoperate with the Sourcegraph SCIP ecosystem.

Grammar (informal, see SCIP `scip.proto` for the canonical reference)::

    <symbol>          ::= <scheme> ' ' <manager> ' ' <package_name>
                          ' ' <package_version> ' ' <descriptor>+
    <scheme>          ::= 'local' | <identifier>     ; e.g. 'scip-python'
    <descriptor>      ::= <namespace> | <type> | <term> | <method>
                          | <type_parameter> | <parameter> | <meta>
    <namespace>       ::= <name> '/'
    <type>            ::= <name> '#'
    <term>            ::= <name> '.'
    <method>          ::= <name> '(' <disambiguator>? ').'
    <type_parameter>  ::= '[' <name> ']'
    <parameter>       ::= '(' <name> ')'
    <meta>            ::= <name> ':'
    <name>            ::= <simple-identifier> | <escaped-identifier>
    <simple-identifier> ::= one or more of [A-Za-z0-9_+$.-]
    <escaped-identifier> ::= '`' (any char, '``' escapes a literal backtick) '`'

Invariants enforced here:

* ``SymbolID.parse(s).to_string() == s`` (round-trip).
* The header (scheme/manager/package/version) is exactly four space-separated
  tokens followed by a single space and the descriptor stream.
* Empty header fields use the placeholder ``'.'`` (matching SCIP convention).

The module is intentionally dependency-free except for ``pydantic-core`` for
the Pydantic v2 integration (see ``__get_pydantic_core_schema__``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class DescriptorKind(StrEnum):
    """SCIP descriptor kinds, identified by their trailing suffix syntax."""

    NAMESPACE = "namespace"  # ``name/``
    TYPE = "type"  # ``name#``
    TERM = "term"  # ``name.``
    METHOD = "method"  # ``name(disambig?).``
    TYPE_PARAMETER = "type_parameter"  # ``[name]``
    PARAMETER = "parameter"  # ``(name)``
    META = "meta"  # ``name:``


@dataclass(frozen=True, slots=True)
class Descriptor:
    """One segment of a SymbolID."""

    name: str
    kind: DescriptorKind
    disambiguator: str = ""

    def __post_init__(self) -> None:
        if self.disambiguator and self.kind is not DescriptorKind.METHOD:
            raise ValueError("disambiguator is only valid for METHOD descriptors")

    def to_string(self) -> str:
        n = _encode_name(self.name)
        if self.kind is DescriptorKind.NAMESPACE:
            return f"{n}/"
        if self.kind is DescriptorKind.TYPE:
            return f"{n}#"
        if self.kind is DescriptorKind.TERM:
            return f"{n}."
        if self.kind is DescriptorKind.META:
            return f"{n}:"
        if self.kind is DescriptorKind.METHOD:
            d = _encode_name(self.disambiguator) if self.disambiguator else ""
            return f"{n}({d})."
        if self.kind is DescriptorKind.TYPE_PARAMETER:
            return f"[{n}]"
        if self.kind is DescriptorKind.PARAMETER:
            return f"({n})"
        raise AssertionError(f"unhandled descriptor kind: {self.kind}")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class SymbolID:
    """A SCIP-encoded symbol identifier.

    Construct via :meth:`parse` from a serialized string, or by composing
    descriptors directly. Instances are hashable and value-equal — they may
    safely live in sets and dict keys.
    """

    scheme: str
    manager: str = "."
    package_name: str = "."
    package_version: str = "."
    descriptors: tuple[Descriptor, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------ ctors
    @classmethod
    def parse(cls, s: str) -> SymbolID:
        """Parse a serialized SCIP symbol. Raises :class:`SymbolParseError`."""
        return _parse_symbol(s)

    # ----------------------------------------------------------- serialization
    def to_string(self) -> str:
        header = f"{self.scheme} {self.manager} {self.package_name} {self.package_version} "
        body = "".join(d.to_string() for d in self.descriptors)
        return header + body

    def __str__(self) -> str:
        return self.to_string()

    # --------------------------------------------------- pydantic v2 support
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        from pydantic_core import core_schema

        def _validate(v: Any) -> SymbolID:
            if isinstance(v, cls):
                return v
            if isinstance(v, str):
                return cls.parse(v)
            raise TypeError(f"cannot convert {type(v).__name__} to SymbolID")

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                str,
                when_used="always",
                return_schema=core_schema.str_schema(),
            ),
        )


class SymbolParseError(ValueError):
    """Raised when a SCIP symbol string cannot be parsed."""


# ---------------------------------------------------------------------------
# Parser internals
# ---------------------------------------------------------------------------


_IDENT_EXTRA = frozenset("_$+-.")


def _is_ident_char(c: str) -> bool:
    """Per scip-go: simple-identifier chars include alphanumerics + ``_$+-.``."""
    return c.isalnum() or c in _IDENT_EXTRA


def _needs_escape(name: str) -> bool:
    """A name needs backtick-escaping if it is empty or contains non-ident chars."""
    if not name:
        return True
    return any(not _is_ident_char(c) for c in name)


def _encode_name(name: str) -> str:
    if not _needs_escape(name):
        return name
    return "`" + name.replace("`", "``") + "`"


def _parse_symbol(s: str) -> SymbolID:
    if not isinstance(s, str):
        raise SymbolParseError(f"symbol must be str, got {type(s).__name__}")
    # Header is 4 space-separated tokens, then ' ', then the descriptor stream.
    # We split on the first 4 spaces; remaining is the descriptor body
    # (which may itself contain spaces inside backtick-escaped names).
    parts = s.split(" ", 4)
    if len(parts) < 5:
        raise SymbolParseError(
            f"invalid SCIP symbol: need at least 5 space-separated fields "
            f"(scheme manager package version descriptors...), got {len(parts)} in {s!r}"
        )
    scheme, manager, pkg, ver, body = parts
    if not scheme:
        raise SymbolParseError("scheme must be non-empty")
    descriptors = tuple(_parse_descriptors(body))
    if not descriptors:
        raise SymbolParseError(f"symbol must have at least one descriptor: {s!r}")
    return SymbolID(
        scheme=scheme,
        manager=manager or ".",
        package_name=pkg or ".",
        package_version=ver or ".",
        descriptors=descriptors,
    )


def _parse_descriptors(s: str) -> list[Descriptor]:
    out: list[Descriptor] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "[":
            name, j = _read_name(s, i + 1)
            if j >= n or s[j] != "]":
                raise SymbolParseError(f"unterminated [type_parameter] at offset {i} in {s!r}")
            out.append(Descriptor(name=name, kind=DescriptorKind.TYPE_PARAMETER))
            i = j + 1
            continue
        if c == "(":
            # Bare '(name)' is a PARAMETER descriptor.
            name, j = _read_name(s, i + 1)
            if j >= n or s[j] != ")":
                raise SymbolParseError(f"unterminated (parameter) at offset {i} in {s!r}")
            out.append(Descriptor(name=name, kind=DescriptorKind.PARAMETER))
            i = j + 1
            continue

        name, j = _read_name(s, i)
        # Trailing-dot recovery: a greedy identifier may have absorbed a final
        # '.' which was actually meant to be the term suffix. If we ran off the
        # end of the input with no remaining suffix character, give back the
        # final '.' to serve as the suffix.
        if j == n and name.endswith("."):
            name = name[:-1]
            j -= 1
        if j >= n:
            raise SymbolParseError(f"missing descriptor suffix after name at offset {i} in {s!r}")
        suffix = s[j]
        if suffix == "/":
            out.append(Descriptor(name=name, kind=DescriptorKind.NAMESPACE))
            i = j + 1
        elif suffix == "#":
            out.append(Descriptor(name=name, kind=DescriptorKind.TYPE))
            i = j + 1
        elif suffix == ":":
            out.append(Descriptor(name=name, kind=DescriptorKind.META))
            i = j + 1
        elif suffix == ".":
            out.append(Descriptor(name=name, kind=DescriptorKind.TERM))
            i = j + 1
        elif suffix == "(":
            disambig, k = _read_name(s, j + 1)
            if k >= n or s[k] != ")":
                raise SymbolParseError(f"unterminated method '(' at offset {j} in {s!r}")
            if k + 1 >= n or s[k + 1] != ".":
                raise SymbolParseError(
                    f"method ')' must be followed by '.' at offset {k + 1} in {s!r}"
                )
            out.append(
                Descriptor(
                    name=name,
                    kind=DescriptorKind.METHOD,
                    disambiguator=disambig,
                )
            )
            i = k + 2
        else:
            raise SymbolParseError(f"unknown descriptor suffix {suffix!r} at offset {j} in {s!r}")
    return out


def _read_name(s: str, i: int) -> tuple[str, int]:
    """Read a single ``<name>`` token. Returns ``(name, next_index)``.

    Supports both simple identifiers and backtick-escaped names. Inside a
    backtick-escaped name, ``''`` (two backticks) encodes a literal backtick.
    """
    n = len(s)
    if i >= n:
        return "", i
    if s[i] == "`":
        return _read_escaped(s, i + 1)
    j = i
    while j < n and _is_ident_char(s[j]):
        j += 1
    return s[i:j], j


def _read_escaped(s: str, i: int) -> tuple[str, int]:
    n = len(s)
    buf: list[str] = []
    j = i
    while j < n:
        if s[j] == "`":
            if j + 1 < n and s[j + 1] == "`":
                buf.append("`")
                j += 2
                continue
            return "".join(buf), j + 1
        buf.append(s[j])
        j += 1
    raise SymbolParseError(f"unterminated escaped name starting at offset {i - 1}")


__all__ = [
    "Descriptor",
    "DescriptorKind",
    "SymbolID",
    "SymbolParseError",
]
