"""The entry-point that ``codemap-aimemory>=0.4.1`` picks up.

``rank(query, project_root, base_candidates)`` returns the top-N
knowledge ids whose chunk embeddings are most similar to the query
embedding. ``codemap-aimemory`` then RRF-fuses our ranking with its
token ranking and multiplies the result by freshness.

Failure modes (all silent, ``codemap recall`` keeps working):

* No semantic store on this project → ``[]``
* Model mismatch (user changed backend without ``--rebuild``) → ``[]``
  with stderr warning
* Backend errors (network down for cloud / model missing for local) →
  ``[]`` with stderr warning"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from codemap_aimemory.freshness import (
    STALE_THRESHOLD,
    compute_freshness,
    load_code_change_map,
)

from codemap_semantic_index import config
from codemap_semantic_index.embedding import build_backend
from codemap_semantic_index.store import ModelMismatch, SemanticStore

__all__ = ["rank"]


#: How many top chunk hits to scan before aggregating to knowledge_id
#: level. We grab more chunks than the final top-K because one knowledge
#: doc usually has multiple chunks → dedup pulls many chunks down to
#: fewer ids.
_TOP_CHUNK_HITS = 50

#: Same demotion as the token-path shared scan (FIX-3d) so the two paths
#: agree about how much a shared hit is downgraded vs a local one.
_SHARED_DEMOTION = 0.7


def rank(
    query: str,
    project_root: Path,
    base_candidates: Iterable[dict[str, Any]],
    *,
    include_shared: bool = False,
    shared_roots: Sequence[Path | str] | None = None,
) -> list[dict[str, Any]]:
    """codemap.recall_hooks entry-point.

    ``base_candidates`` is part of the hook protocol but unused here.

    When ``include_shared=True`` and ``shared_roots`` is non-empty, every
    shared root's ``_semantic/`` store is also queried — FIX-3e. Shared
    hits carry ``source: shared`` and their ``score`` is multiplied by
    :data:`_SHARED_DEMOTION` so an equal-similarity local hit always wins.
    Shared stores whose ``model_id`` ≠ the active backend's are silently
    skipped (with a stderr warning) — refusing to mix vector spaces.
    """
    # Cheap pre-check: if no store anywhere asks to be searched, skip
    # building the (expensive — torch import / model load) backend.
    local_store = SemanticStore(project_root)
    candidate_shared = [Path(s) for s in shared_roots] if (include_shared and shared_roots) else []
    if not local_store.is_built and not any(
        (Path(p) / ".ai-memory" / "_semantic").is_dir() for p in candidate_shared
    ):
        return []

    cfg = _effective_config()
    try:
        backend = build_backend(cfg)
    except Exception as exc:
        sys.stderr.write(f"semantic recall: failed to build backend: {exc}\n")
        return []

    try:
        q_vec = backend.encode([query])
    except Exception as exc:
        sys.stderr.write(f"semantic recall: failed to encode query: {exc}\n")
        return []

    if q_vec.shape[0] != 1:
        sys.stderr.write(f"semantic recall: bad query vector shape {q_vec.shape}\n")
        return []

    local_entries = _scan_store(
        project_root, q_vec[0], backend.model_id, source="local", demotion=1.0
    )

    if not include_shared or not shared_roots:
        return _sorted_unique(local_entries)

    seen_ids = {e["knowledge_id"] for e in local_entries}
    merged: list[dict[str, Any]] = list(local_entries)
    for sr in shared_roots:
        shared_path = Path(sr)
        if not (shared_path / ".ai-memory" / "_semantic").is_dir():
            continue
        shared_entries = _scan_store(
            shared_path,
            q_vec[0],
            backend.model_id,
            source="shared",
            demotion=_SHARED_DEMOTION,
        )
        for se in shared_entries:
            if se["knowledge_id"] in seen_ids:
                continue  # local wins on id collision
            seen_ids.add(se["knowledge_id"])
            merged.append(se)
    return _sorted_unique(merged)


def _scan_store(
    root: Path,
    query_vec: np.ndarray,
    backend_model_id: str,
    *,
    source: str,
    demotion: float,
) -> list[dict[str, Any]]:
    """Load ``<root>/.ai-memory/_semantic/`` and return knowledge candidates
    ranked by cosine similarity. Returns ``[]`` (with a stderr warning when
    appropriate) on any error rather than raising, so one bad store can't
    take recall down.
    """
    store = SemanticStore(root)
    if not store.is_built:
        return []
    chunks = store.load_chunks()
    vectors = store.load_vectors()
    if not chunks or vectors is None or vectors.shape[0] == 0:
        return []

    try:
        store.assert_model_matches(backend_model_id)
    except ModelMismatch as exc:
        sys.stderr.write(f"semantic recall ({source} @ {root}): {exc}\n")
        return []

    if vectors.shape[1] != query_vec.shape[0]:
        sys.stderr.write(
            f"semantic recall ({source} @ {root}): vector dim mismatch "
            f"(query={query_vec.shape[0]} vs store={vectors.shape[1]})\n"
        )
        return []

    sims = vectors @ query_vec
    top_n = min(_TOP_CHUNK_HITS, sims.shape[0])
    top_idx = np.argpartition(-sims, top_n - 1)[:top_n]
    top_idx = top_idx[np.argsort(-sims[top_idx])]

    code_change_map = load_code_change_map(root / ".ai-memory")
    best_for_id: dict[str, tuple[float, dict[str, Any]]] = {}
    for idx in top_idx:
        ch = chunks[idx]
        raw_score = float(sims[idx])
        adjusted = raw_score * demotion
        existing = best_for_id.get(ch.knowledge_id)
        if existing is not None and existing[0] >= adjusted:
            continue
        freshness = _freshness_for_chunk(ch, root, code_change_map)
        entry = {
            "knowledge_id": ch.knowledge_id,
            "type": _CATEGORY_TYPE_HINT.get(ch.category, ""),
            "category": ch.category,
            "title": ch.title or ch.knowledge_id,
            "summary": ch.h2_title or "",
            "file": ch.source_yml,
            "score": round(adjusted, 4),
            "freshness_score": freshness,
            "stale": freshness < STALE_THRESHOLD,
            "matched_chunk": ch.chunk_id,
            "source": source,
        }
        best_for_id[ch.knowledge_id] = (adjusted, entry)
    return [e for _, e in best_for_id.values()]


def _sorted_unique(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by score desc with stable tie-break on knowledge_id."""
    return sorted(entries, key=lambda e: (-e["score"], e["knowledge_id"]))


def _effective_config() -> config.EmbeddingConfig:
    """Resolve config in CLI flag > env > file > defaults order.

    Hook context has no CLI flags, so env > file > defaults."""
    cfg = config.load()
    # Env overrides — same priority story as codemap llm config.
    api_key = config.env_default(
        "CODEMAP_EMBED_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "ZHIPUAI_API_KEY",
        "VOYAGE_API_KEY",
    )
    base_url = config.env_default("CODEMAP_EMBED_BASE_URL", "OPENAI_BASE_URL")
    model_env = config.env_default("CODEMAP_EMBED_MODEL")
    dim_env = config.env_default("CODEMAP_EMBED_DIMENSIONS")
    backend_env = config.env_default("CODEMAP_EMBED_BACKEND")

    if backend_env:
        cfg.backend = backend_env
    if api_key:
        cfg.api_key = api_key
    if base_url:
        cfg.base_url = base_url
    if model_env:
        cfg.model = model_env
    if dim_env:
        with contextlib.suppress(ValueError):
            cfg.dimensions = int(dim_env)
    return cfg


_CATEGORY_TYPE_HINT: dict[str, str] = {
    "rules": "business_rule",
    "business": "business_process",
    "modules": "module_map",
    "cases": "case",
    "pitfalls": "pitfall",
}


def _freshness_for_chunk(
    chunk: Any,
    project_root: Path,
    code_change_map: dict[str, int],
) -> float:
    """Compute freshness for the chunk's source yml. Falls back to 1.0
    if the yml can't be read."""
    import yaml

    yml_path = project_root / chunk.source_yml
    if not yml_path.is_file():
        return 1.0
    try:
        kn = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return 1.0
    if not isinstance(kn, dict):
        return 1.0
    return compute_freshness(kn, code_change_map)
