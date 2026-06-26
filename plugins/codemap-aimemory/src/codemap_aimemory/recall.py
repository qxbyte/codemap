"""Token-based knowledge recall — backs ``codemap recall`` (P3-1).

Given a free-text query and a project root, scans
``<project_root>/.ai-memory/knowledge/{rules,business,modules,cases,
pitfalls}/*.yml`` and ranks knowledge by token overlap with each yml's
searchable fields (title / tags / statement / related_code / etc.).
Returns the top-K results as a JSON/YAML-safe dict ready for an Agent
to inject into ``requirements.md`` (specode's phase-0 context recall).

Pure function — no IO outside ``yaml.safe_load`` on knowledge yml and
``_global/entities.yml``. Deliberate non-goals for this v1:

* No embedding / vector search — pure token overlap (English `\\w+`
  words ≥ 2 chars + Chinese char-bigrams). Good enough for the recall
  layer; semantic search lands in P1-3.
* No reranking by freshness (P4-1) — every match scores equally
  regardless of staleness for now.
"""

from __future__ import annotations

import importlib.metadata as _md
import re
import warnings
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from codemap_aimemory.freshness import (
    STALE_THRESHOLD,
    compute_freshness,
    load_code_change_map,
)

__all__ = ["RECALL_HOOK_GROUP", "RRF_K", "recall", "tokenize"]

#: Entry-point group used to discover external ranking hooks (e.g. the
#: ``codemap-semantic-index`` plugin's embedding-based hook).
RECALL_HOOK_GROUP = "codemap.recall_hooks"

#: RRF constant; the canonical value from Cormack 2009. Tunable in tests.
RRF_K = 60


_KNOWLEDGE_SUBDIRS: tuple[str, ...] = (
    "rules",
    "business",
    "modules",
    "cases",
    "pitfalls",
)

_CATEGORY_TYPE_HINT: dict[str, str] = {
    "rules": "business_rule",
    "business": "business_process",
    "modules": "module_map",
    "cases": "case",
    "pitfalls": "pitfall",
}


def recall(
    query: str,
    project_root: Path,
    top_k: int = 5,
    types: list[str] | None = None,
    with_content: bool = False,
) -> dict[str, Any]:
    """Find the top-K knowledge yml most relevant to ``query``.

    ``types``, when provided, restricts to those category names
    (``rules`` / ``business`` / ``modules`` / ``cases`` / ``pitfalls``).

    ``with_content=True`` adds a ``content`` dict to each result with
    the category's core fields (``rule.statement/why/exceptions/...``,
    ``pit.symptom/fix/...``, ``case.implementation_summary/...``, ...)
    so downstream automation can inject knowledge *content* rather than
    just bare wikilinks. specode 3.1+ uses this in step 2.2 injection.

    Every result also carries ``freshness_score ∈ [0, 1]`` and
    ``stale: bool`` (true when score < 0.5). Ranking multiplies score
    by freshness so stale knowledge fades behind fresher hits.

    Returns a dict with ``query``, ``tokens`` (parsed), ``matched_entities``
    (from ``_global/entities.yml``), and ``knowledge`` (list of result
    dicts sorted by ranked score desc).
    """
    ai_mem = project_root / ".ai-memory"
    tokens = tokenize(query)
    matched_entities = _match_entities(ai_mem / "_global" / "entities.yml", tokens)
    code_change_map = load_code_change_map(ai_mem)

    knowledge_root = ai_mem / "knowledge"
    candidates: list[dict[str, Any]] = []
    if knowledge_root.is_dir() and tokens:
        wanted = set(types) if types else None
        for subdir in _KNOWLEDGE_SUBDIRS:
            if wanted is not None and subdir not in wanted:
                continue
            for yml_file in sorted((knowledge_root / subdir).glob("*.yml")):
                kn = _load_yaml(yml_file)
                if not isinstance(kn, dict):
                    continue
                score = _score(kn, tokens)
                if score == 0:
                    continue
                freshness = compute_freshness(kn, code_change_map)
                ranked_score = round(score * freshness, 3)
                entry: dict[str, Any] = {
                    "knowledge_id": kn.get("knowledge_id") or yml_file.stem,
                    "type": kn.get("type") or _CATEGORY_TYPE_HINT.get(subdir, ""),
                    "category": subdir,
                    "title": _extract_title(kn),
                    "summary": _extract_summary(kn),
                    "score": score,
                    "ranked_score": ranked_score,
                    "freshness_score": freshness,
                    "stale": freshness < STALE_THRESHOLD,
                    "file": str(yml_file.relative_to(project_root)),
                }
                if with_content:
                    entry["content"] = _extract_content(kn, subdir)
                candidates.append(entry)

    # Sort by ranked score (token overlap multiplied by freshness); stable tiebreak by id.
    candidates.sort(key=lambda c: (-c["ranked_score"], c["knowledge_id"]))

    # Discover external rankers (e.g. codemap-semantic-index embedding hook)
    # and fuse via RRF. No hooks installed → token-only path is unchanged
    # (back-compat for every 0.4.0 caller).
    hooks = _load_recall_hooks()
    if hooks:
        candidates = _fuse_with_hooks(
            token_candidates=candidates,
            hooks=hooks,
            query=query,
            project_root=project_root,
        )

    return {
        "query": query,
        "tokens": sorted(tokens),
        "matched_entities": matched_entities,
        "knowledge": candidates[:top_k],
    }


# ---------- recall hooks (P1-3 enablement) ----------


def _load_recall_hooks() -> list[tuple[str, Callable[..., Iterable[dict[str, Any]]]]]:
    """Discover registered ranking hooks via the ``codemap.recall_hooks``
    entry-point group. Each entry-point's ``name`` is used as the ranker
    label in RRF; the loaded object MUST be callable.

    Failures (missing module, bad attr, non-callable) are warned and skipped
    so one broken plugin can't take recall down.
    """
    try:
        eps = _md.entry_points(group=RECALL_HOOK_GROUP)
    except Exception as exc:  # pragma: no cover - importlib.metadata edge
        warnings.warn(f"failed to enumerate {RECALL_HOOK_GROUP}: {exc}", stacklevel=2)
        return []

    out: list[tuple[str, Callable[..., Iterable[dict[str, Any]]]]] = []
    for ep in eps:
        try:
            obj = ep.load()
        except Exception as exc:
            warnings.warn(f"recall hook '{ep.name}' failed to load: {exc}", stacklevel=2)
            continue
        if not callable(obj):
            warnings.warn(f"recall hook '{ep.name}' is not callable: {obj!r}", stacklevel=2)
            continue
        out.append((ep.name, obj))
    return out


def _fuse_with_hooks(
    token_candidates: list[dict[str, Any]],
    hooks: list[tuple[str, Callable[..., Iterable[dict[str, Any]]]]],
    query: str,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Run every hook, then merge their rankings with the token ranking
    via Reciprocal Rank Fusion (k=:data:`RRF_K`).

    Hook contract: ``hook(query, project_root, base_candidates) ->
    Iterable[dict]``. Each dict MUST carry ``knowledge_id``; SHOULD carry
    the same shape as a token candidate (``type``/``category``/``title``/
    ``summary``/``file``/``freshness_score``/``stale``). Hook entries
    with the same ``knowledge_id`` as a token entry are de-duplicated —
    token-side metadata wins (it's the authoritative shape).

    Final ``ranked_score = rrf_score * freshness_score`` so the P4-2
    freshness behaviour is preserved end-to-end.
    """
    rankings: list[tuple[str, list[dict[str, Any]]]] = [("token", list(token_candidates))]
    for name, hook in hooks:
        try:
            result = hook(query=query, project_root=project_root, base_candidates=token_candidates)
        except Exception as exc:
            warnings.warn(f"recall hook '{name}' raised at call time: {exc}", stacklevel=2)
            continue
        if not isinstance(result, list):
            try:
                result = list(result)
            except TypeError:
                warnings.warn(
                    f"recall hook '{name}' returned non-iterable: {result!r}",
                    stacklevel=2,
                )
                continue
        cleaned = [e for e in result if isinstance(e, dict) and e.get("knowledge_id")]
        rankings.append((name, cleaned))

    # RRF over the union of all rankers.
    score_map: dict[str, float] = {}
    meta_map: dict[str, dict[str, Any]] = {}
    contributing_rankers: dict[str, list[str]] = {}

    for ranker_name, ranking in rankings:
        # Each ranker decides its own internal sort by its own score field;
        # we just trust the order we received. Token recall already passed
        # the list sorted by ranked_score; hooks are expected to do the same.
        for rank_idx, entry in enumerate(ranking, start=1):
            kid = entry.get("knowledge_id")
            if not kid:
                continue
            score_map[kid] = score_map.get(kid, 0.0) + 1.0 / (RRF_K + rank_idx)
            # First-seen metadata wins. Token ranker comes first → its
            # richer shape (with content / freshness / file path) overrides.
            if kid not in meta_map:
                meta_map[kid] = dict(entry)
            contributing_rankers.setdefault(kid, []).append(ranker_name)

    fused: list[dict[str, Any]] = []
    for kid, rrf_score in score_map.items():
        meta = dict(meta_map[kid])
        freshness = meta.get("freshness_score")
        if not isinstance(freshness, (int, float)):
            freshness = 1.0
        meta["rrf_score"] = round(rrf_score, 4)
        meta["ranked_score"] = round(rrf_score * freshness, 4)
        meta["ranked_by"] = sorted(set(contributing_rankers.get(kid, [])))
        fused.append(meta)

    fused.sort(key=lambda c: (-c["ranked_score"], c["knowledge_id"]))
    return fused


# ---------- tokenizer ----------


_EN_WORD_RE = re.compile(r"[a-z0-9_]+")
_CN_RUN_RE = re.compile(r"[一-鿿]+")


def tokenize(text: str) -> set[str]:
    """English/digit words (≥ 2 chars) + Chinese char-bigrams.

    Chinese segmentation without an external dependency (jieba etc.) is
    crude; bigrams give acceptable recall for the few-word queries that
    show up at the requirements stage.
    """
    if not text:
        return set()
    lowered = text.lower()
    out: set[str] = set()
    for word in _EN_WORD_RE.findall(lowered):
        if len(word) >= 2:
            out.add(word)
    for run in _CN_RUN_RE.findall(lowered):
        if len(run) == 1:
            out.add(run)
        else:
            for i in range(len(run) - 1):
                out.add(run[i : i + 2])
    return out


# ---------- scoring ----------


def _score(kn: dict[str, Any], tokens: set[str]) -> int:
    searchable = " ".join(_searchable_strings(kn)).lower()
    score = 0
    for tok in tokens:
        if tok in searchable:
            score += 1
    # Title hits weighted higher
    title = _extract_title(kn).lower()
    if title:
        for tok in tokens:
            if tok in title:
                score += 1
    return score


def _searchable_strings(kn: dict[str, Any]) -> list[str]:
    """Flatten every string-ish field of a knowledge yml into a list."""
    out: list[str] = []
    for key in (
        "knowledge_id",
        "title",
        "statement",
        "case_id",
        "pit_id",
        "implementation_summary",
        "symptom",
        "context",
        "root_cause",
        "trigger",
        "end_state",
        "scope",
    ):
        v = kn.get(key)
        if isinstance(v, str):
            out.append(v)

    for key in ("tags", "related_requirements", "related_knowledge", "affects"):
        out.extend(v for v in (kn.get(key) or []) if isinstance(v, str))

    for item in kn.get("related_code") or []:
        if isinstance(item, dict):
            for k in ("entity", "file"):
                v = item.get(k)
                if isinstance(v, str):
                    out.append(v)

    for list_key in (
        "trigger_conditions",
        "exceptions",
        "enforcement",
        "lessons",
        "fix",
        "prevention",
        "changed_files",
        "bugs_encountered",
    ):
        for v in kn.get(list_key) or []:
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, dict):
                out.extend(sub for sub in v.values() if isinstance(sub, str))

    return out


def _extract_title(kn: dict[str, Any]) -> str:
    for k in ("title", "statement", "case_id", "pit_id", "knowledge_id"):
        v = kn.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _extract_summary(kn: dict[str, Any]) -> str:
    for k in ("statement", "implementation_summary", "symptom", "context"):
        v = kn.get(k)
        if isinstance(v, str) and v:
            return v.strip().splitlines()[0][:240]
    return ""


# ---------- content extraction (for --with-content) ----------


_CONTENT_FIELDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "rules": (
        "statement",
        "why",
        "trigger_conditions",
        "exceptions",
        "enforcement",
    ),
    "business": (
        "trigger",
        "end_state",
        "steps",
        "data_flow",
        "ui_constraints",
    ),
    "modules": (
        "scope",
        "primary_entity",
        "columns",
        "shard",
        "call_chain",
    ),
    "cases": (
        "implementation_summary",
        "key_decisions",
        "bugs_encountered",
        "lessons",
        "review_findings",
        "acceptance_status",
        "changed_files",
    ),
    "pitfalls": (
        "symptom",
        "root_cause",
        "fix",
        "prevention",
        "affects",
    ),
}


def _extract_content(kn: dict[str, Any], category: str) -> dict[str, Any]:
    """Pull the category-specific core fields out of a knowledge yml.

    Returned dict is ready to render into requirements.md (specode step
    2.2 injection) — only keeps non-empty fields so the rendered
    markdown stays compact."""
    fields = _CONTENT_FIELDS_BY_CATEGORY.get(category, ())
    out: dict[str, Any] = {}
    for key in fields:
        value = kn.get(key)
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out


# ---------- _global/entities.yml ----------


def _match_entities(path: Path, tokens: set[str]) -> list[str]:
    if not tokens or not path.is_file():
        return []
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return []
    entities = data.get("entities") or []
    out: list[str] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        eid = ent.get("id")
        if not isinstance(eid, str):
            continue
        eid_lower = eid.lower()
        if any(tok in eid_lower for tok in tokens):
            out.append(eid)
    return sorted(out)


def _load_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
