"""Swift indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_swift._version import __version__
from codemap_swift.indexer import SwiftIndexer

__all__ = ["SwiftIndexer", "__version__"]
