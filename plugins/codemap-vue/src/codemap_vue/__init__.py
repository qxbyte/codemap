"""Vue SFC indexer plugin for CodeMap.

The entry-point group ``codemap.indexers`` discovers this class
automatically once ``codemap-vue`` is installed alongside the host
CodeMap CLI.
"""

from __future__ import annotations

from codemap_vue.indexer import VueIndexer

__version__ = VueIndexer.version

__all__ = ["VueIndexer", "__version__"]
