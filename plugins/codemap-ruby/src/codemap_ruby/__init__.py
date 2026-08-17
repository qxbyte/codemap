"""Ruby indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_ruby.indexer import RubyIndexer

__version__ = RubyIndexer.version

__all__ = ["RubyIndexer", "__version__"]
