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

import re
from pathlib import Path
from typing import Any

import yaml

__all__ = ["recall", "tokenize"]


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
) -> dict[str, Any]:
    """Find the top-K knowledge yml most relevant to ``query``.

    ``types``, when provided, restricts to those category names
    (``rules`` / ``business`` / ``modules`` / ``cases`` / ``pitfalls``).
    Returns a dict with ``query``, ``tokens`` (parsed), ``matched_entities``
    (from ``_global/entities.yml``), and ``knowledge`` (list of result
    dicts sorted by score desc).
    """
    ai_mem = project_root / ".ai-memory"
    tokens = tokenize(query)
    matched_entities = _match_entities(ai_mem / "_global" / "entities.yml", tokens)

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
                candidates.append(
                    {
                        "knowledge_id": kn.get("knowledge_id") or yml_file.stem,
                        "type": kn.get("type") or _CATEGORY_TYPE_HINT.get(subdir, ""),
                        "category": subdir,
                        "title": _extract_title(kn),
                        "summary": _extract_summary(kn),
                        "score": score,
                        "file": str(yml_file.relative_to(project_root)),
                    }
                )

    candidates.sort(key=lambda c: (-c["score"], c["knowledge_id"]))  # stable secondary sort by id
    return {
        "query": query,
        "tokens": sorted(tokens),
        "matched_entities": matched_entities,
        "knowledge": candidates[:top_k],
    }


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
