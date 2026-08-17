"""C indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_c.indexer import CIndexer

__version__ = CIndexer.version

__all__ = ["CIndexer", "__version__"]
