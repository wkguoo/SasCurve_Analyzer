"""Cross-process advisory locking for a study output directory."""

from __future__ import annotations

import errno
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class StudyLockError(BlockingIOError):
    """Raised when another process is already writing the same study output."""


def _lock_path(output_dir: Path) -> Path:
    name = output_dir.name or "root"
    return output_dir.parent / f".{name}.study.lock"


def _is_lock_contention(error: OSError) -> bool:
    return (
        error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(error, "winerror", None) in {33, 36}
    )


@contextmanager
def study_lock(output_dir: str | Path) -> Iterator[None]:
    """Acquire a non-blocking OS lock associated with one canonical output path.

    The lock file is deliberately retained after release. Removing it could let
    two processes lock different inodes for the same output path.
    """
    output = Path(output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(output)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(lock_path, flags, 0o666), "r+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if _is_lock_contention(exc):
                raise StudyLockError(f"Study output is busy; another process holds its lock: {output}") from exc
            raise
        try:
            # Lock the byte range before initializing it. Both OS APIs permit
            # locking an empty file; only its owner may write the marker.
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
