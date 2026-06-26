"""Knowledge freshness scoring — backs P4-1 + P4-2.

A knowledge yml goes stale when:

1. Its ``updated_at`` is far in the past, or
2. The code files it references (``related_code[].file``) have churned
   a lot since the knowledge was written.

``compute_freshness(kn, code_change_map, today)`` returns a `[0, 1]`
score — 1 means fresh, 0 means very stale. Recall multiplies this into
the ranking score so older / out-of-sync knowledge fades behind
fresher hits, and marks hits with ``stale: true`` when the score drops
below 0.5 so downstream tooling (specode requirements injection) can
visually flag them.

Pure module — no IO outside ``_load_yaml`` on the entities yml.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "STALE_THRESHOLD",
    "compute_freshness",
    "load_code_change_map",
]

# Tunable constants. The defaults are deliberately gentle:
#  - 180-day half-life means a year-old knowledge with zero code churn
#    still scores ~0.25 (down from 1.0); not aggressive enough to bury
#    foundational rules that legitimately don't change often.
#  - 0.05 churn weight means a `related_code` file that's changed 20
#    times in the last 90 days halves the score on the code-factor side.
_HALF_LIFE_DAYS = 180.0
_CODE_CHURN_WEIGHT = 0.05

#: Hits scoring strictly less than this are flagged ``stale: true``.
STALE_THRESHOLD = 0.5


def compute_freshness(
    knowledge: Mapping[str, Any],
    code_change_map: Mapping[str, int],
    today: datetime.date | None = None,
) -> float:
    """Return a freshness score in ``[0, 1]`` for one knowledge dict.

    ``code_change_map`` is ``{file_path: change_count_90d}`` — pre-built
    once per recall call by :func:`load_code_change_map`. Knowledge
    without ``related_code`` is scored on age only.
    """
    today = today or datetime.date.today()

    updated_at = knowledge.get("updated_at")
    if isinstance(updated_at, str):
        try:
            kn_date = datetime.date.fromisoformat(updated_at)
        except ValueError:
            kn_date = today
    elif isinstance(updated_at, datetime.date):
        kn_date = updated_at
    else:
        kn_date = today

    age_days = max(0, (today - kn_date).days)
    age_factor = math.exp(-age_days / _HALF_LIFE_DAYS)

    related_files: list[str] = []
    for item in knowledge.get("related_code") or []:
        if isinstance(item, Mapping):
            f = item.get("file")
            if isinstance(f, str):
                related_files.append(f)

    total_changes = sum(code_change_map.get(f, 0) for f in related_files)
    code_factor = 1.0 / (1.0 + _CODE_CHURN_WEIGHT * total_changes)

    return round(age_factor * code_factor, 3)


def load_code_change_map(ai_memory_root: Path) -> dict[str, int]:
    """Build ``{file: change_count_90d}`` from ``entities/{functions,tables}.yml``.

    Missing / unreadable yml is silently skipped — freshness on a project
    that has never been indexed by codemap just degrades to age-only,
    which is still useful."""
    out: dict[str, int] = {}
    for name in ("functions.yml", "tables.yml"):
        path = ai_memory_root / "entities" / name
        data = _load_yaml(path)
        if not isinstance(data, list):
            continue
        for ent in data:
            if not isinstance(ent, Mapping):
                continue
            f = ent.get("file")
            c = ent.get("change_count_90d")
            if isinstance(f, str) and isinstance(c, int) and (f not in out or out[f] < c):
                out[f] = c
    return out


def _load_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
