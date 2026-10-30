"""Named run locks: one process at a time per job (collect, later change detection), across processes.

    with run_lock("collect"):
        ...

fcntl.flock on data/ci/<name>.lock, non-blocking: a second holder gets RunLocked at once, with the first holder's pid
and start time. The kernel releases the lock when the holder exits, however it exits (exception, kill), so a stale
lock file never blocks; the file itself is left in place and simply re-locked.
"""
import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from config.settings import DATA_DIR

LOCK_DIR = DATA_DIR / "ci"


class RunLocked(RuntimeError):
    """Another process holds the lock."""

    def __init__(self, name: str, holder: dict):
        self.name, self.holder = name, holder
        pid, since = holder.get("pid", "?"), holder.get("since", "?")
        super().__init__(f"another run is in progress (pid {pid}, since {since})")


def _read_holder(fd: int) -> dict:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        data = json.loads(os.read(fd, 4096).decode("utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


@contextmanager
def run_lock(name: str, lock_dir: Path | None = None) -> Iterator[Path]:
    """Hold <lock_dir>/<name>.lock for the duration of the block; raise RunLocked if it is already held."""
    lock_dir = lock_dir or LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{name}.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RunLocked(name, _read_holder(fd)) from None
        holder = {"pid": os.getpid(), "since": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(holder).encode("utf-8"))
        try:
            yield path
        finally:
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
