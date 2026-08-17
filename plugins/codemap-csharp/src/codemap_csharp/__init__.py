"""C# indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_csharp.indexer import CSharpIndexer

__version__ = CSharpIndexer.version

__all__ = ["CSharpIndexer", "__version__"]
