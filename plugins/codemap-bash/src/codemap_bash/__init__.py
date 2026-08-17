"""Bash indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_bash.indexer import BashIndexer

__version__ = BashIndexer.version

__all__ = ["BashIndexer", "__version__"]
