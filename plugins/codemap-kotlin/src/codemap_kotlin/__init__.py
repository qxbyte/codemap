"""Kotlin indexer plugin for CodeMap."""

from __future__ import annotations

from codemap_kotlin.indexer import KotlinIndexer

__version__ = KotlinIndexer.version

__all__ = ["KotlinIndexer", "__version__"]
