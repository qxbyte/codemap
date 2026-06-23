"""Language-neutral Git change-frequency analysis (change hotspots).

Pure read-only: shells out to ``git log`` and tallies how many commits in the
window touched each file. Returns ``{}`` when the path is not a git repo or
git is unavailable — never raises for those cases (ADR-007 graceful
degradation).
"""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

__all__ = ["change_counts"]


def change_counts(project_root: Path, *, since_days: int = 90) -> dict[str, int]:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "log",
                f"--since={since_days}.days.ago",
                "--name-only",
                "--pretty=format:",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    counter: Counter[str] = Counter()
    for line in proc.stdout.splitlines():
        path = line.strip()
        if path:
            counter[path] += 1
    return dict(counter)
