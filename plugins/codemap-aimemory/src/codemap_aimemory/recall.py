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

import datetime
import importlib.metadata as _md
import re
import warnings
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml

from codemap_aimemory.freshness import (
    STALE_THRESHOLD,
    compute_freshness,
    load_code_change_map,
)
from codemap_aimemory.knowledge_schema import (
    CATEGORIES as _KNOWLEDGE_SUBDIRS,
)
from codemap_aimemory.knowledge_schema import (
    CATEGORY_TYPE as _CATEGORY_TYPE_HINT,
)
from codemap_aimemory.knowledge_schema import (
    CONTENT_FIELDS_BY_CATEGORY as _CONTENT_FIELDS_BY_CATEGORY,
)

__all__ = [
    "RECALL_HOOK_GROUP",
    "RRF_K",
    "extract_entities",
    "extract_query_focus",
    "recall",
    "tokenize",
]

#: Entry-point group used to discover external ranking hooks (e.g. the
#: ``codemap-semantic-index`` plugin's embedding-based hook).
RECALL_HOOK_GROUP = "codemap.recall_hooks"

#: RRF constant; the canonical value from Cormack 2009. Tunable in tests.
RRF_K = 60

#: Demotion factor applied to ``ranked_score`` of ``source: shared`` hits
#: so that a local rule wins ties (FIX-3d). Empirically: 0.7 lets a clearly
#: better shared hit still surface near the top, but keeps the project's
#: own knowledge above same-token-overlap shared hits.
SHARED_DEMOTION_FACTOR = 0.7


def recall(
    query: str,
    project_root: Path,
    top_k: int = 5,
    types: list[str] | None = None,
    with_content: bool = False,
    today: datetime.date | None = None,
    shared_roots: Sequence[Path | str] | None = None,
    include_shared: bool = False,
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

    ``include_shared=True`` additionally scans every directory in
    ``shared_roots`` (each shaped like a project root) for cross-project
    team knowledge (FIX-3d). Shared hits are labelled ``source: shared``
    and demoted by :data:`SHARED_DEMOTION_FACTOR` so local rules win
    ties; on ``knowledge_id`` collision the local entry wins outright.

    Returns a dict with ``query``, ``tokens`` (parsed), ``matched_entities``
    (from ``_global/entities.yml``), and ``knowledge`` (list of result
    dicts sorted by ranked score desc).
    """
    ai_mem = project_root / ".ai-memory"
    tokens = tokenize(query)
    matched_entities = _match_entities(ai_mem / "_global" / "entities.yml", tokens)
    code_change_map = load_code_change_map(ai_mem)

    candidates = _scan_root(
        root=project_root,
        tokens=tokens,
        code_change_map=code_change_map,
        types=types,
        with_content=with_content,
        today=today,
        source="local",
        demotion=1.0,
    )

    if include_shared and shared_roots:
        seen_ids = {c["knowledge_id"] for c in candidates}
        for sr in shared_roots:
            shared_path = Path(sr)
            if not shared_path.is_dir():
                warnings.warn(f"shared knowledge root not found: {shared_path}", stacklevel=2)
                continue
            shared_cands = _scan_root(
                root=shared_path,
                tokens=tokens,
                code_change_map=code_change_map,
                types=types,
                with_content=with_content,
                today=today,
                source="shared",
                demotion=SHARED_DEMOTION_FACTOR,
            )
            for sc in shared_cands:
                if sc["knowledge_id"] in seen_ids:
                    continue  # local wins on id collision
                seen_ids.add(sc["knowledge_id"])
                candidates.append(sc)

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
            include_shared=include_shared,
            shared_roots=shared_roots,
        )

    code_context = _build_code_context(ai_mem, matched_entities, top_k, query=query)

    return {
        "query": query,
        "tokens": sorted(tokens),
        "matched_entities": matched_entities,
        "code_context": code_context,
        "knowledge": candidates[:top_k],
    }


def _scan_root(
    *,
    root: Path,
    tokens: set[str],
    code_change_map: dict[str, Any],
    types: list[str] | None,
    with_content: bool,
    today: datetime.date | None,
    source: str,
    demotion: float,
) -> list[dict[str, Any]]:
    """Token-score every knowledge yml under ``<root>/.ai-memory/knowledge/``.

    Reused for both the project's own root (``source="local"``) and for
    each opt-in cross-project root (``source="shared"``, with a
    ``demotion`` < 1 applied to ``ranked_score``).
    """
    knowledge_root = root / ".ai-memory" / "knowledge"
    if not knowledge_root.is_dir() or not tokens:
        return []

    wanted = set(types) if types else None
    out: list[dict[str, Any]] = []
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
            freshness = compute_freshness(kn, code_change_map, today=today)
            ranked_score = round(score * freshness * demotion, 3)
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
                "file": str(yml_file.relative_to(root)),
                "source": source,
            }
            if with_content:
                entry["content"] = _extract_content(kn, subdir)
            out.append(entry)
    return out


# ---------- code_context: cold-start L1 fallback (FIX-3b) ----------


def _build_code_context(
    ai_mem: Path,
    matched_ids: list[str],
    top_k: int,
    *,
    query: str = "",
) -> list[dict[str, Any]]:
    """Enrich the matched entity ids with their L1 structure (signature /
    callers / callees / related tables) and any knowledge_refs from _global.

    This is the bridge that makes the *first* spec on a project useful: even
    with an empty ``knowledge/``, the spec author sees the relevant code map.

    v0.9 痛点 #2: each entry carries ``precision: 'high' | 'low'`` —
    ``high`` when the entity's short name (after stripping the ``cls-`` /
    ``fn-`` / ``tbl-`` / ``mod-`` / ``field-`` / ``route-`` / ``sym-``
    prefix) precisely matches an entity-shaped token extracted from the
    query (FQN suffix matching included, same logic as
    ``entity_exact_hook``). Sort key promotes high precision ahead of
    low, so when ``matched_entities`` flood with namesakes (e.g.
    ``ItTicketMapper.updateStatus`` + ``MediaFileMapper.updateStatus``)
    the genuinely-named ones surface first.
    """
    if not matched_ids:
        return []
    wanted = set(matched_ids)

    by_id: dict[str, dict[str, Any]] = {}
    for name in ("functions.yml", "tables.yml", "files.yml", "modules.yml"):
        data = _load_yaml(ai_mem / "entities" / name)
        if not isinstance(data, list):
            continue
        for ent in data:
            if isinstance(ent, dict) and ent.get("id") in wanted:
                by_id.setdefault(ent["id"], ent)

    refs_by_id = _load_knowledge_refs(ai_mem / "_global" / "entities.yml")

    # Build the precision lookup once from the query.
    query_entities = set(extract_entities(query)) if query else set()

    out: list[dict[str, Any]] = []
    for eid in matched_ids:
        ent = by_id.get(eid, {})
        precision = _precision_for_entity_id(eid, query_entities)
        entry: dict[str, Any] = {
            "id": eid,
            "type": ent.get("type"),
            "file": ent.get("file"),
            "signature": ent.get("signature"),
            "called_by": ent.get("called_by") or [],
            "calls": ent.get("calls") or [],
            "related_tables": ent.get("related_tables") or [],
            "business_meaning": ent.get("business_meaning"),
            "change_count_90d": ent.get("change_count_90d"),
            "knowledge_refs": refs_by_id.get(eid, []),
            "precision": precision,
        }
        out.append(entry)

    # Sort: high-precision first; then most-churned (likeliest hotspots);
    # finally stable by id.
    out.sort(
        key=lambda e: (
            0 if e["precision"] == "high" else 1,
            -(e.get("change_count_90d") or 0),
            e["id"],
        )
    )
    return out[:top_k]


_ID_PREFIX_RE = re.compile(r"^(cls|fn|tbl|mod|field|route|sym)-")


def _precision_for_entity_id(entity_id: str, query_entities: set[str]) -> str:
    """Return ``'high'`` if ``entity_id``'s short name (after stripping the
    type prefix) is in ``query_entities`` directly OR via FQN suffix
    matching. Otherwise ``'low'``.

    Mirrors ``entity_exact_hook._entity_match`` (FQN suffix bidirectional)
    so the two code paths agree on what counts as a precision match.
    """
    if not query_entities:
        return "low"
    short = _ID_PREFIX_RE.sub("", entity_id, count=1)
    # Strip the collision-disambiguating ``-<8hex>`` suffix that
    # ``entities/ids.py`` appends when two entities share the same prefix
    # + short name. Otherwise ``fn-updateStatus-4f6656b5`` would never
    # match query token ``updateStatus``.
    short = re.sub(r"-[0-9a-f]{8}$", "", short)
    for q in query_entities:
        if q == short:
            return "high"
        if "." in q and q.rsplit(".", 1)[-1] == short:
            return "high"
        if "." in short and short.rsplit(".", 1)[-1] == q:
            return "high"
    return "low"


def _load_knowledge_refs(path: Path) -> dict[str, list[str]]:
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for ent in data.get("entities") or []:
        if isinstance(ent, dict) and isinstance(ent.get("id"), str):
            refs = ent.get("knowledge_refs")
            out[ent["id"]] = refs if isinstance(refs, list) else []
    return out


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
    include_shared: bool = False,
    shared_roots: Sequence[Path | str] | None = None,
) -> list[dict[str, Any]]:
    """Run every hook, then merge their rankings with the token ranking
    via Reciprocal Rank Fusion (k=:data:`RRF_K`).

    Hook contract: ``hook(query, project_root, base_candidates,
    [include_shared,] [shared_roots,]) -> Iterable[dict]``. The two
    trailing kwargs were added in 0.4.4 (FIX-3e) — hooks built against
    0.4.1/0.4.3 signatures still work via TypeError fallback below.
    Each dict MUST carry ``knowledge_id``; SHOULD carry the same shape
    as a token candidate. Token-side metadata wins on id collision (it's
    the authoritative shape).

    Final ``ranked_score = rrf_score * freshness_score`` so the P4-2
    freshness behaviour is preserved end-to-end.
    """
    rankings: list[tuple[str, list[dict[str, Any]]]] = [("token", list(token_candidates))]
    for name, hook in hooks:
        try:
            result = hook(
                query=query,
                project_root=project_root,
                base_candidates=token_candidates,
                include_shared=include_shared,
                shared_roots=shared_roots,
            )
        except TypeError:
            # Pre-0.4.4 hook signature without include_shared / shared_roots.
            try:
                result = hook(
                    query=query,
                    project_root=project_root,
                    base_candidates=token_candidates,
                )
            except Exception as exc:
                warnings.warn(
                    f"recall hook '{name}' raised at call time: {exc}",
                    stacklevel=2,
                )
                continue
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

# ---------- query focus (FIX-3a) ----------

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_ENTITY_RES = (
    re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"),  # dotted FQN
    re.compile(r"/[A-Za-z0-9_][A-Za-z0-9_/{}-]*"),  # api path
    re.compile(r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"),  # CamelCase / PascalCase
    re.compile(r"\b[a-z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"),  # camelCase (lower-first; v0.9 #2)
    re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+"),  # snake_case
)


def extract_entities(text: str) -> list[str]:
    """Pull entity-shaped tokens (dotted FQN / api path / CamelCase /
    snake_case) out of arbitrary text, preserving first-seen order.

    Shared by :func:`extract_query_focus` (FIX-3a) and the entity-exact
    recall hook (FIX-3c) so both paths agree on what "an entity" looks like.
    """
    if not text:
        return []
    entities: list[str] = []
    seen: set[str] = set()
    for pattern in _ENTITY_RES:
        for match in pattern.findall(text):
            if match not in seen:
                seen.add(match)
                entities.append(match)
    return entities


def extract_query_focus(text: str, max_chars: int = 1500) -> str:
    """Trim a whole spec document down to its salient retrieval signal.

    Passing an entire ``requirements.md`` as the query (the ``--from-spec``
    default) token-explodes the bigram tokenizer so nearly everything matches
    and ranking degrades to noise (AI-EDS ISSUE-6). This keeps only the
    headings + entity-like tokens (table / class / api-path / FQN), dropping
    the YAML frontmatter and prose filler. Falls back to the (capped) body
    when too little structured signal is extracted, so short queries are
    untouched.
    """
    if not text:
        return ""
    body = _FRONTMATTER_RE.sub("", text, count=1)

    headings = [ln.lstrip("#").strip() for ln in body.splitlines() if ln.lstrip().startswith("#")]
    entities = extract_entities(body)

    focus = "\n".join([*headings, *entities])
    if len(focus.strip()) < 80:
        return body.strip()[:max_chars]
    return focus[:max_chars]


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
