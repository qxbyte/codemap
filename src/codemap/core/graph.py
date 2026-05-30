"""Call-graph algorithms (depth-limited BFS, bidirectional shortest path).

These run against any :class:`codemap.core.store.ReadOnlyStore`. They are the
algorithmic core of the ``codemap trace`` command and are also reused by
later Bridges that need to walk relationships.

Two operations:

* :func:`walk_chain` — breadth-first downstream traversal from a starting
  symbol, capped at ``max_depth``. Returns a tree-shaped :class:`ChainNode`
  rooted at the start node. Cycles are broken by deduplication.

* :func:`shortest_path` — bidirectional BFS between ``start`` and ``end``
  through outgoing (callees) edges. Returns the list of edges forming the
  shortest path, or ``None`` if none exists within ``max_depth`` hops from
  each side.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemap.core.models import Edge
    from codemap.core.store import ReadOnlyStore
    from codemap.core.symbol import SymbolID


@dataclass
class ChainNode:
    """One node in a downstream traversal tree."""

    symbol_id: SymbolID
    depth: int
    incoming_edge: Edge | None = None
    """The edge that brought us to this node (None for the root)."""
    children: list[ChainNode] = field(default_factory=list)


def walk_chain(
    start: SymbolID,
    store: ReadOnlyStore,
    *,
    max_depth: int = 10,
) -> ChainNode:
    """Breadth-first downstream walk, returning a tree rooted at ``start``.

    Each visited node appears at most once across the whole tree (the first
    time it is reached). Cycles therefore manifest as missing children on
    repeated nodes.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")
    root = ChainNode(symbol_id=start, depth=0)
    if max_depth == 0:
        return root

    visited: set[str] = {str(start)}
    frontier: deque[ChainNode] = deque([root])
    while frontier:
        node = frontier.popleft()
        if node.depth >= max_depth:
            continue
        for edge in store.callees(node.symbol_id, depth=1):
            target_key = str(edge.target)
            if target_key in visited:
                continue
            visited.add(target_key)
            child = ChainNode(
                symbol_id=edge.target,
                depth=node.depth + 1,
                incoming_edge=edge,
            )
            node.children.append(child)
            frontier.append(child)
    return root


def shortest_path(
    start: SymbolID,
    end: SymbolID,
    store: ReadOnlyStore,
    *,
    max_depth: int = 10,
) -> list[Edge] | None:
    """Bidirectional BFS over outgoing edges. Returns the list of edges that
    form the shortest path from ``start`` to ``end``, or ``None``.

    The two frontiers expand alternately. As soon as a node appears in both
    visited sets, the two halves are stitched into the full path.
    """
    if max_depth < 1:
        raise ValueError("max_depth must be >= 1")
    s_key = str(start)
    e_key = str(end)
    if s_key == e_key:
        return []

    # Each visited map: node_key -> (parent_key | None, edge_from_parent | None)
    forward_parents: dict[str, tuple[str | None, Edge | None]] = {s_key: (None, None)}
    backward_parents: dict[str, tuple[str | None, Edge | None]] = {e_key: (None, None)}
    forward_layer = [start]
    backward_layer = [end]

    # Each round expands **both** frontiers by one hop. ``max_depth`` thus
    # caps the depth of each side independently, so the total path length
    # reachable is up to ``2 * max_depth``.
    for _ in range(max_depth):
        forward_layer, meeting = _expand(
            forward_layer, store, forward_parents, backward_parents, direction="fwd"
        )
        if meeting is not None:
            return _stitch(meeting, forward_parents, backward_parents)
        if not forward_layer:
            return None
        backward_layer, meeting = _expand(
            backward_layer, store, backward_parents, forward_parents, direction="bwd"
        )
        if meeting is not None:
            return _stitch(meeting, forward_parents, backward_parents)
        if not backward_layer:
            return None
    return None


def _expand(
    layer: list[SymbolID],
    store: ReadOnlyStore,
    own_parents: dict[str, tuple[str | None, Edge | None]],
    other_parents: dict[str, tuple[str | None, Edge | None]],
    *,
    direction: str,
) -> tuple[list[SymbolID], str | None]:
    """Push one frontier outwards by one hop. Returns the new layer and an
    optional meeting-point key if the frontier intersects ``other_parents``.
    """
    next_layer: list[SymbolID] = []
    for node in layer:
        edges = store.callees(node, depth=1) if direction == "fwd" else store.callers(node, depth=1)
        for edge in edges:
            neighbour = edge.target if direction == "fwd" else edge.source
            key = str(neighbour)
            parent_key = str(node)
            if key in own_parents:
                continue
            own_parents[key] = (parent_key, edge)
            if key in other_parents:
                return next_layer, key
            next_layer.append(neighbour)
    return next_layer, None


def _stitch(
    meeting: str,
    forward_parents: dict[str, tuple[str | None, Edge | None]],
    backward_parents: dict[str, tuple[str | None, Edge | None]],
) -> list[Edge]:
    """Build the path edges from start → meeting and meeting → end."""
    fwd_edges: list[Edge] = []
    cur: str | None = meeting
    while cur is not None:
        parent, edge = forward_parents[cur]
        if edge is None:
            break
        fwd_edges.append(edge)
        cur = parent
    fwd_edges.reverse()

    bwd_edges: list[Edge] = []
    cur = meeting
    while cur is not None:
        parent, edge = backward_parents[cur]
        if edge is None:
            break
        bwd_edges.append(edge)
        cur = parent

    return fwd_edges + bwd_edges


__all__ = ["ChainNode", "shortest_path", "walk_chain"]
