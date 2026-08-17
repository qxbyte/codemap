"""C++ indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_cpp._version import __version__
from codemap_cpp.indexer import CppIndexer

__all__ = ["CppIndexer", "__version__"]
