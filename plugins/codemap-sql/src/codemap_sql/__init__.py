"""SQL indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_sql._version import __version__
from codemap_sql.indexer import SqlIndexer

__all__ = ["SqlIndexer", "__version__"]
