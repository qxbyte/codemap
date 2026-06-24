"""Optional LLM enrichment overlay.

Two contract surfaces:

* :func:`load_enrichment` — read every ``enrichment/*.yml`` in a folder,
  return a ``symbol_id → payload dict`` map; missing folder → ``{}``. Used
  by :class:`AiMemoryEmitter` to merge ``business_meaning`` /
  ``related_rules`` at emit time.
* :func:`enrich` — for every function/method symbol in the store, call the
  injected ``LlmClient.describe(...)`` to produce the explanation payload
  and write one file per symbol under ``enrichment/``. Files use a sha1
  prefix of the SCIP id as the filename so re-runs are idempotent and
  collision-free. ``changed_only=True`` skips symbols whose enrichment
  file already exists.

The core deterministic index never reads these files; only the emitter
does, and even then only to fill the explanation slots — structural fields
remain whatever the indexers + bridges produced.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

import yaml

from codemap.core.store import ReadOnlyStore

__all__ = ["LlmClient", "enrich", "load_enrichment"]

_FN_KINDS = frozenset({"method", "function"})


class LlmClient(Protocol):
    model: str

    def describe(self, symbol: dict[str, Any]) -> dict[str, Any]: ...


def load_enrichment(dir_: Path) -> dict[str, dict[str, Any]]:
    if not dir_.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(dir_.glob("*.yml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        sid = data.get("symbol_id")
        if isinstance(sid, str):
            out[sid] = data
    return out


def enrich(
    store: ReadOnlyStore,
    llm: LlmClient,
    out_dir: Path,
    *,
    generated_at: str,
    changed_only: bool = False,
) -> list[str]:
    enr_dir = _resolve_enr_dir(out_dir)
    enr_dir.mkdir(parents=True, exist_ok=True)
    existing = load_enrichment(enr_dir) if changed_only else {}
    written: list[str] = []
    for sym in store.iter_symbols():
        if sym.kind not in _FN_KINDS:
            continue
        sid = str(sym.id)
        if changed_only and sid in existing:
            continue
        result = llm.describe(
            {
                "symbol_id": sid,
                "signature": sym.signature,
                "file": str(sym.file),
            }
        )
        payload = {
            "symbol_id": sid,
            "business_meaning": result.get("business_meaning"),
            "related_rules": result.get("related_rules", []),
            "confidence": "llm",
            "source_model": llm.model,
            "generated_at": generated_at,
        }
        target = enr_dir / f"{hashlib.sha1(sid.encode('utf-8')).hexdigest()[:12]}.yml"
        fd, tmp = tempfile.mkstemp(dir=enr_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
            os.replace(tmp, target)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        written.append(target.name)
    return written


def _resolve_enr_dir(out_dir: Path) -> Path:
    """Accept either ``<project>/.ai-memory`` or its ``enrichment`` subdir."""
    if out_dir.name == "enrichment":
        return out_dir
    if out_dir.name == ".ai-memory":
        return out_dir / "enrichment"
    return out_dir / ".ai-memory" / "enrichment"
