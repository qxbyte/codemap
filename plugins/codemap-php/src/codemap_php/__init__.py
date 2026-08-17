"""PHP indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_php.indexer import PhpIndexer

__version__ = PhpIndexer.version

__all__ = ["PhpIndexer", "__version__"]
