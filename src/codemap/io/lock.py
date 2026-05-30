"""Process-level file locking for `.codemap/.lock` (ADR-008).

Uses ``fcntl.flock`` on POSIX. On Windows, falls back to ``msvcrt.locking``.
Both paths share the same context-manager API.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO


class LockTimeoutError(RuntimeError):
    """Raised when the lock cannot be acquired before the deadline."""


_DEFAULT_TIMEOUT = 30.0
_POLL_INTERVAL = 0.1


@contextmanager
def file_lock(path: Path, *, timeout: float = _DEFAULT_TIMEOUT) -> Iterator[IO[str]]:
    """Acquire an exclusive lock on ``path`` (creating it if missing).

    Writes a diagnostic line (PID + ISO timestamp) into the lock file on
    acquisition. Raises :class:`LockTimeoutError` if the lock cannot be
    acquired within ``timeout`` seconds.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    f = path.open("a+", encoding="utf-8")
    try:
        while True:
            try:
                _acquire(f)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(
                        f"could not acquire lock on {path} within {timeout}s; "
                        f"check {path} for the holder's PID"
                    ) from None
                time.sleep(_POLL_INTERVAL)
        try:
            f.seek(0)
            f.truncate()
            f.write(f"pid={os.getpid()} acquired_at={datetime.now(UTC).isoformat()}\n")
            f.flush()
            yield f
        finally:
            _release(f)
    finally:
        f.close()


if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI
    import msvcrt

    def _acquire(f: IO[str]) -> None:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(str(exc)) from exc

    def _release(f: IO[str]) -> None:
        with contextlib.suppress(OSError):
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire(f: IO[str]) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(f: IO[str]) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


__all__ = ["LockTimeoutError", "file_lock"]
