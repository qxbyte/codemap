"""Java indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_java.indexer import JavaIndexer

__version__ = JavaIndexer.version

__all__ = ["JavaIndexer", "__version__"]
