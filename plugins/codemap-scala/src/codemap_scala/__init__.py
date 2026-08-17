"""Scala indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_scala._version import __version__
from codemap_scala.indexer import ScalaIndexer

__all__ = ["ScalaIndexer", "__version__"]
