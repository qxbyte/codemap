"""Manifest read/write with schema_version enforcement (ADR-006)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from codemap.core.models import SCHEMA_VERSION, Manifest

logger = logging.getLogger(__name__)


class SchemaVersionError(ValueError):
    """Raised when the on-disk schema is incompatible with this CodeMap build."""


def _parse_semver(s: str) -> tuple[int, int, int]:
    parts = s.split(".")
    if len(parts) < 3:
        raise SchemaVersionError(f"invalid schema_version {s!r}: expected MAJOR.MINOR.PATCH")
    try:
        major, minor, patch = (int(p) for p in parts[:3])
    except ValueError as exc:
        raise SchemaVersionError(f"non-integer component in schema_version {s!r}") from exc
    return major, minor, patch


def check_schema_version(on_disk: str, *, expected: str = SCHEMA_VERSION) -> None:
    """Raise :class:`SchemaVersionError` if on-disk schema is incompatible.

    Compatibility rules (per ADR-006):

    * Missing / empty → hard fail
    * Major mismatch → hard fail
    * Minor newer on disk than this build → hard fail (we don't know future fields)
    * Minor older on disk → log warning, continue
    * Patch mismatch → silent
    """
    if not on_disk:
        raise SchemaVersionError("manifest.schema_version is empty or missing")
    on_disk_t = _parse_semver(on_disk)
    expected_t = _parse_semver(expected)
    if on_disk_t[0] != expected_t[0]:
        raise SchemaVersionError(
            f"incompatible schema_version: on-disk={on_disk}, expected={expected}; "
            f"run `codemap index --rebuild`"
        )
    if on_disk_t[1] > expected_t[1]:
        raise SchemaVersionError(
            f"on-disk schema {on_disk} is newer than this CodeMap supports "
            f"({expected}); upgrade CodeMap"
        )
    if on_disk_t[1] < expected_t[1]:
        logger.warning(
            "on-disk schema_version %s is older than current %s; will be rewritten on next commit",
            on_disk,
            expected,
        )


def manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def load_manifest(root: Path) -> Manifest:
    """Load and validate manifest from ``<root>/manifest.json``.

    Raises :class:`SchemaVersionError` on incompatible schema.
    """
    p = manifest_path(root)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SchemaVersionError(f"manifest at {p} is not a JSON object")
    version = raw.get("schema_version", "")
    check_schema_version(version if isinstance(version, str) else "")
    return Manifest.model_validate(raw)


def dump_manifest(m: Manifest) -> bytes:
    return m.model_dump_json(indent=2).encode("utf-8")


__all__ = [
    "SchemaVersionError",
    "check_schema_version",
    "dump_manifest",
    "load_manifest",
    "manifest_path",
]
