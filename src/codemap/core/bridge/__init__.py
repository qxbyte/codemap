"""Cross-scheme bridge abstractions.

Bridges resolve relationships between symbols of different schemes after all
indexers have finished. They are language-neutral by construction (ADR-L001):
bridges operate on Symbol/Edge data, not on language-specific AST.
"""

from __future__ import annotations
