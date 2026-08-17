"""Bash indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_bash._version import __version__
from codemap_bash.indexer import BashIndexer

__all__ = ["BashIndexer", "__version__"]
