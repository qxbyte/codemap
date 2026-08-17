"""Swift indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_swift.indexer import SwiftIndexer

__version__ = SwiftIndexer.version

__all__ = ["SwiftIndexer", "__version__"]
