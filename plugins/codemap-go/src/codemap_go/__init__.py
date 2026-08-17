"""Go indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_go.indexer import GoIndexer

__version__ = GoIndexer.version

__all__ = ["GoIndexer", "__version__"]
