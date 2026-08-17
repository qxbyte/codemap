"""TypeScript indexer plugin for CodeMap.

The entry-point group ``codemap.indexers`` discovers this class
automatically once ``codemap-typescript`` is installed alongside the
host CodeMap CLI.
"""

from __future__ import annotations

from codemap_typescript.indexer import TypeScriptIndexer

__version__ = TypeScriptIndexer.version

__all__ = ["TypeScriptIndexer", "__version__"]
