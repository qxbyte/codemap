"""Go indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_go._version import __version__
from codemap_go.indexer import GoIndexer

__all__ = ["GoIndexer", "__version__"]
