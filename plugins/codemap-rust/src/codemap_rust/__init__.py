"""Rust indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_rust._version import __version__
from codemap_rust.indexer import RustIndexer

__all__ = ["RustIndexer", "__version__"]
