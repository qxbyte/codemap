"""SQL indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_sql.indexer import SqlIndexer

__version__ = SqlIndexer.version

__all__ = ["SqlIndexer", "__version__"]
