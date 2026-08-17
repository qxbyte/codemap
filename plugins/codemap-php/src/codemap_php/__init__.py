"""PHP indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_php._version import __version__
from codemap_php.indexer import PhpIndexer

__all__ = ["PhpIndexer", "__version__"]
