"""Rust indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_rust.indexer import RustIndexer

__version__ = RustIndexer.version

__all__ = ["RustIndexer", "__version__"]
