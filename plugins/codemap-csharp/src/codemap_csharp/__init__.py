"""C# indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_csharp._version import __version__
from codemap_csharp.indexer import CSharpIndexer

__all__ = ["CSharpIndexer", "__version__"]
