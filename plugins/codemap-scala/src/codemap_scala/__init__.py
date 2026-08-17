"""Scala indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_scala.indexer import ScalaIndexer

__version__ = ScalaIndexer.version

__all__ = ["ScalaIndexer", "__version__"]
