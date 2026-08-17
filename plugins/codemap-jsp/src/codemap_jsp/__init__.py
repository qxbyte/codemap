"""JavaServer Pages (JSP) indexer plugin for CodeMap.

The entry-point group ``codemap.indexers`` discovers this class
automatically once ``codemap-jsp`` is installed alongside the host
CodeMap CLI.
"""

from __future__ import annotations

from codemap_jsp.indexer import JspIndexer

__version__ = JspIndexer.version

__all__ = ["JspIndexer", "__version__"]
