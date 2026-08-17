"""C++ indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_cpp.indexer import CppIndexer

__version__ = CppIndexer.version

__all__ = ["CppIndexer", "__version__"]
