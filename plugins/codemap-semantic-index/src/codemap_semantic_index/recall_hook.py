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
from collections.abc import Iterable
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


def rank(
    query: str,
    project_root: Path,
    base_candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """codemap.recall_hooks entry-point.

    ``base_candidates`` is the token ranker's output; we don't currently
    use it but accept it per the hook protocol so future versions can
    e.g. boost ids the token side already loved."""
    store = SemanticStore(project_root)
    if not store.is_built:
        return []
    chunks = store.load_chunks()
    vectors = store.load_vectors()
    if not chunks or vectors is None or vectors.shape[0] == 0:
        return []

    cfg = _effective_config()
    try:
        backend = build_backend(cfg)
    except Exception as exc:
        sys.stderr.write(f"semantic recall: failed to build backend: {exc}\n")
        return []

    # Refuse to mix vector spaces.
    try:
        store.assert_model_matches(backend.model_id)
    except ModelMismatch as exc:
        sys.stderr.write(f"semantic recall: {exc}\n")
        return []

    try:
        q_vec = backend.encode([query])
    except Exception as exc:
        sys.stderr.write(f"semantic recall: failed to encode query: {exc}\n")
        return []

    if q_vec.shape[0] != 1 or q_vec.shape[1] != vectors.shape[1]:
        sys.stderr.write(
            f"semantic recall: query vector shape {q_vec.shape} incompatible "
            f"with store shape {vectors.shape}\n"
        )
        return []

    # Cosine similarity == dot product since both sides are L2-normalised.
    sims = vectors @ q_vec[0]
    # Top-N chunk indices
    top_n = min(_TOP_CHUNK_HITS, sims.shape[0])
    top_idx = np.argpartition(-sims, top_n - 1)[:top_n]
    # Sort the top-N by similarity desc
    top_idx = top_idx[np.argsort(-sims[top_idx])]

    # Aggregate chunks → knowledge_id (best chunk score wins)
    best_for_id: dict[str, tuple[float, dict[str, Any]]] = {}
    code_change_map = load_code_change_map(project_root / ".ai-memory")

    for idx in top_idx:
        ch = chunks[idx]
        score = float(sims[idx])
        existing = best_for_id.get(ch.knowledge_id)
        if existing is not None and existing[0] >= score:
            continue
        # Build a candidate entry with the standard shape the hook
        # contract asks for. Freshness lookup needs the yml.
        freshness = _freshness_for_chunk(ch, project_root, code_change_map)
        entry = {
            "knowledge_id": ch.knowledge_id,
            "type": _CATEGORY_TYPE_HINT.get(ch.category, ""),
            "category": ch.category,
            "title": ch.title or ch.knowledge_id,
            "summary": ch.h2_title or "",
            "file": ch.source_yml,
            "score": round(score, 4),
            "freshness_score": freshness,
            "stale": freshness < STALE_THRESHOLD,
            "matched_chunk": ch.chunk_id,
        }
        best_for_id[ch.knowledge_id] = (score, entry)

    # Sort knowledge entries by score desc; this is the order recall.py
    # will use to derive RRF rank.
    ordered = sorted(
        (e for _, e in best_for_id.values()),
        key=lambda e: -e["score"],
    )
    return ordered


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
