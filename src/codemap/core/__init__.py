"""Pure-business core: data models, SymbolID, graph algorithms, query semantics.

Strict dependency rule (ADR-003): `core` MUST NOT import from `cli`, `io`,
`indexers`, or `mcp`. Protocols defined here are implemented in outer layers.
"""

from __future__ import annotations
