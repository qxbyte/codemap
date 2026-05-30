"""Atomic file writes for ``.codemap/`` persistence (ADR-008).

All on-disk writes go through :func:`atomic_write`: data lands in a
``<name>.tmp.<pid>`` sibling, is fsynced, and only then ``os.replace``-d into
place. A crash mid-write leaves the original file intact; the leftover ``.tmp``
is removed at next startup by :func:`sweep_stale_tmp_files`.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


@contextmanager
def atomic_write(path: Path, *, mode: str = "wb") -> Iterator[IO[bytes]]:
    """Yield a binary file handle that becomes ``path`` only on clean exit.

    The default ``mode`` is ``"wb"``. The directory is created if missing.
    On exception, the temporary file is removed and the exception re-raised.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        f: IO[bytes] = tmp.open(mode)
        try:
            yield f
            f.flush()
            os.fsync(f.fileno())
        finally:
            f.close()
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def sweep_stale_tmp_files(
    directory: Path,
    *,
    min_age_seconds: float = 5.0,
) -> int:
    """Remove ``*.tmp.<pid>`` files left by previous crashed runs.

    Files newer than ``min_age_seconds`` are kept (they may belong to an
    active write). Files whose ``<pid>`` is still alive on the current host
    are also kept. Returns the number of files actually removed.
    """
    if not directory.exists():
        return 0
    now = time.time()
    removed = 0
    for f in directory.iterdir():
        # ".tmp.<pid>" must be the trailing suffix(es); cheaper than parsing.
        name = f.name
        idx = name.rfind(".tmp.")
        if idx < 0:
            continue
        pid_part = name[idx + len(".tmp.") :]
        if not pid_part.isdigit():
            continue
        try:
            if (now - f.stat().st_mtime) < min_age_seconds:
                continue
        except OSError:
            continue
        if _pid_alive(int(pid_part)):
            continue
        try:
            f.unlink()
        except OSError:
            continue
        removed += 1
    return removed


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False
    return True


__all__ = ["atomic_write", "sweep_stale_tmp_files"]
