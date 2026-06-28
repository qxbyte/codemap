"""Deterministic writer for the knowledge contract (FIX-2).

`write_knowledge(project_root, category, payload)` is the single entry both
specode-distill (LLM-authored payloads) and task-swarm (mechanically-built
payloads) call. It owns every deterministic action:

* id derivation (``knowledge_ids``),
* ``schema_version`` / ``created_at`` / ``updated_at`` / ``version`` stamping,
* same-id merge — ``cases`` supersede (overwrite + version bump, keep
  ``created_at``); the other four are append-only (preserve structural fields,
  append ``related_requirements`` / ``related_knowledge`` / ``source_files``,
  and ``seen_again_in`` for pitfalls),
* atomic dual write of yml + md twin (same stem),
* red lines: refuse to write under an unmounted ``/Volumes`` drive.

The md *body* (prose / ascii / wikilinks) is authored upstream and preserved
verbatim (方案A); only the frontmatter is machine-rendered. When no body is
supplied (task-swarm path), a minimal body is rendered from the fields so the
twin md is never empty.

Never raises for content problems — returns ``errors`` so callers (especially
task-swarm's non-fatal ingest) can decide. Only programming bugs propagate.
"""

from __future__ import annotations

import contextlib
import datetime
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from codemap_aimemory.knowledge_ids import case_id, derive_id, normalize_id, pit_id
from codemap_aimemory.knowledge_schema import (
    CATEGORIES,
    CATEGORY_TYPE,
    SCHEMA_VERSION,
)
from codemap_aimemory.knowledge_schema import (
    validate as validate_schema,
)

__all__ = ["write_knowledge"]

#: yml fields that, on an append-only merge, accumulate rather than overwrite.
_APPEND_LIST_FIELDS: tuple[str, ...] = (
    "related_requirements",
    "related_knowledge",
    "source_files",
)

#: identity / lifecycle fields the writer manages itself — never copied from
#: incoming payload during an append-only merge (the writer has already stamped
#: them).
_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "knowledge_id",
        "type",
        "version",
        "created_at",
        "updated_at",
        "status",
        "confidence",
    }
)

#: md frontmatter is a compact subset of the yml (the rest is in the yml twin).
_MD_FRONTMATTER_FIELDS: tuple[str, ...] = (
    "knowledge_id",
    "type",
    "version",
    "updated_at",
    "tags",
    "related_requirements",
    "related_knowledge",
    "related_code",
)


def write_knowledge(
    project_root: Path,
    category: str,
    payload: dict[str, Any],
    *,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    today = today or datetime.date.today()
    project_root = Path(project_root)

    if category not in CATEGORIES:
        return _error(f"unknown category: {category!r} (expected one of {CATEGORIES})")

    mount_err = _mount_check(project_root)
    if mount_err:
        return _error(mount_err)

    knowledge_id = _resolve_id(category, payload)
    if knowledge_id is None:
        return _error(
            "cannot derive knowledge_id: payload needs one of "
            "knowledge_id / spec_id (cases) / signature (pitfalls) / title"
        )

    yml_dir = project_root / ".ai-memory" / "knowledge" / category
    md_dir = project_root / "knowledge-base" / category
    yml_path = yml_dir / f"{knowledge_id}.yml"
    md_path = md_dir / f"{knowledge_id}.md"

    existing = _load_yaml(yml_path) if yml_path.is_file() else None
    kn, action = _assemble(category, knowledge_id, payload, existing, today)

    errors = validate_schema(kn, category)
    if errors:
        return {"knowledge_id": knowledge_id, "errors": errors, "action": "rejected"}

    yml_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(yml_path, _dump_yaml(kn))
    _atomic_write_text(md_path, _render_md(kn, payload.get("md_body")))

    return {
        "knowledge_id": knowledge_id,
        "yml_path": str(yml_path),
        "md_path": str(md_path),
        "action": action,
        "errors": [],
    }


# ---------- id resolution ----------


def _resolve_id(category: str, payload: dict[str, Any]) -> str | None:
    raw = payload.get("knowledge_id")
    if isinstance(raw, str) and raw.strip():
        return normalize_id(category, raw)
    if category == "cases":
        spec_id = payload.get("spec_id")
        if isinstance(spec_id, str) and spec_id.strip():
            return case_id(spec_id)
    if category == "pitfalls":
        sig = payload.get("signature")
        if isinstance(sig, str) and sig.strip():
            return pit_id(sig)
    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        return derive_id(category, title)
    return None


# ---------- assembly + merge ----------


def _assemble(
    category: str,
    knowledge_id: str,
    payload: dict[str, Any],
    existing: dict[str, Any] | None,
    today: datetime.date,
) -> tuple[dict[str, Any], str]:
    fields = dict(payload.get("fields") or {})
    spec_id = payload.get("spec_id")
    today_str = today.isoformat()

    if existing is None:
        kn: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "knowledge_id": knowledge_id,
            "type": CATEGORY_TYPE[category],
            "version": 1,
            "created_at": today_str,
            "updated_at": today_str,
            "status": fields.pop("status", None) or "active",
            "confidence": fields.pop("confidence", None) or "high",
        }
        kn.update(fields)
        _ensure_requirement_links(kn, spec_id)
        return kn, "created"

    # merge against existing
    kn = dict(existing)
    prev_version = kn.get("version")
    kn["version"] = (prev_version if isinstance(prev_version, int) else 1) + 1
    kn["updated_at"] = today_str
    kn.setdefault("schema_version", SCHEMA_VERSION)
    kn["type"] = CATEGORY_TYPE[category]
    fields.pop("status", None)
    fields.pop("confidence", None)

    if category == "cases":
        # supersede: this spec's re-run rewrites the implementation wholesale
        for key, value in fields.items():
            kn[key] = value
        _ensure_requirement_links(kn, spec_id)
        return kn, "superseded"

    # append-only for rules / business / modules / pitfalls:
    # preserve structural fields, only accumulate the list links below.
    # 0.4.9: also fill in *blank* structural fields from incoming payload —
    # earlier writes that created the yml with only frontmatter (round 2/3
    # rule body loss) can now be backfilled by a follow-up write carrying the
    # real fields, without losing append-only safety for fields already
    # populated (those stay untouched).
    for key, value in fields.items():
        if key in _APPEND_LIST_FIELDS or key in _IDENTITY_FIELDS:
            continue
        if _is_blank(kn.get(key)):
            kn[key] = value
    for key in _APPEND_LIST_FIELDS:
        merged = _merge_list(kn.get(key), fields.get(key))
        if merged:
            kn[key] = merged
    _ensure_requirement_links(kn, spec_id)
    if category == "pitfalls" and isinstance(spec_id, str) and spec_id:
        kn["seen_again_in"] = _merge_list(kn.get("seen_again_in"), [spec_id])
    return kn, "merged"


def _is_blank(value: Any) -> bool:
    return value in (None, "", [], {}) or (isinstance(value, str) and not value.strip())


def _ensure_requirement_links(kn: dict[str, Any], spec_id: Any) -> None:
    if isinstance(spec_id, str) and spec_id:
        kn["related_requirements"] = _merge_list(kn.get("related_requirements"), [spec_id])


def _merge_list(existing: Any, incoming: Any) -> list:
    out: list = []
    for src in (existing, incoming):
        if isinstance(src, list):
            for item in src:
                if item not in out:
                    out.append(item)
        elif isinstance(src, str) and src and src not in out:
            out.append(src)
    return out


# ---------- md rendering (frontmatter machine; body upstream) ----------


def _render_md(kn: dict[str, Any], md_body: str | None) -> str:
    fm = {k: kn[k] for k in _MD_FRONTMATTER_FIELDS if k in kn and kn[k] not in (None, "", [], {})}
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    lines = ["---", front.rstrip(), "---", ""]
    if md_body and md_body.strip():
        lines.append(md_body.rstrip() + "\n")
    else:
        lines.append(_minimal_body(kn))
    return "\n".join(lines)


def _minimal_body(kn: dict[str, Any]) -> str:
    """Render a minimal but non-empty body from the yml fields (task-swarm
    path, which has no LLM narrative). Skips machine/identity fields."""
    title = kn.get("title") or kn.get("statement") or kn.get("knowledge_id", "")
    out: list[str] = [f"# {title}".rstrip(), ""]
    skip = set(_MD_FRONTMATTER_FIELDS) | {
        "schema_version",
        "knowledge_id",
        "created_at",
        "updated_at",
        "status",
        "confidence",
        "source_spec",
        "source_files",
        "title",
        "version",
        "type",
    }
    for key, value in kn.items():
        if key in skip or value in (None, "", [], {}):
            continue
        out.append(f"## {key}")
        out.append("")
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend(f"- {item}" for item in value)
        else:
            out.append(f"```yaml\n{yaml.safe_dump(value, allow_unicode=True).rstrip()}\n```")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------- io ----------


def _mount_check(project_root: Path) -> str | None:
    p = str(project_root)
    if p.startswith("/Volumes/"):
        parts = p.split("/")
        if len(parts) >= 3 and parts[2]:
            mount = "/Volumes/" + parts[2]
            if not os.path.isdir(mount):
                return f"external drive not mounted: {mount} (挂载) — refusing to write"
    return None


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)


def _error(message: str) -> dict[str, Any]:
    return {"knowledge_id": None, "errors": [message], "action": "rejected"}
