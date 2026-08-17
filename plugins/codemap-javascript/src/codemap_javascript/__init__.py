"""JavaScript / JSX indexer plugin for CodeMap.

The entry-point group ``codemap.indexers`` discovers this class
automatically once ``codemap-javascript`` is installed alongside the
host CodeMap CLI.
"""

from __future__ import annotations

from codemap_javascript.indexer import JavaScriptIndexer

__version__ = JavaScriptIndexer.version

__all__ = ["JavaScriptIndexer", "__version__"]
