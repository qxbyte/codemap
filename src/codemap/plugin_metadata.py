"""Helpers for plugin distribution metadata."""

from __future__ import annotations

from importlib import metadata


def package_version(distribution: str) -> str:
    """Return an installed distribution version or the source-tree fallback."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "0.0.0.dev0"
