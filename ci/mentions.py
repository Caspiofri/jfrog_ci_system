"""Full-page mention counts kept beside a run: output/runs/<run_id>.mentions.json ({id: {mentions, mentions_jfrog,
fetched}}), written by ci.backfill_mentions for runs made before packets carried them. The run JSONL is never
changed; readers overlay the side file onto items that have no counts of their own.
"""
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

from ci.config import canonical_counts

log = logging.getLogger(__name__)

SIDE_SUFFIX = ".mentions.json"


def side_path(runs_dir: Path, run_id: str) -> Path | None:
    if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        return None
    return runs_dir / f"{run_id}{SIDE_SUFFIX}"


def load_side(runs_dir: Path, run_id: str) -> dict[str, dict]:
    path = side_path(runs_dir, run_id)
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("ignoring unreadable mentions side file %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def attach(items: list[dict], runs_dir: Path | None) -> list[dict]:
    """Items with the side file's counts filled in where an item has none (its own counts always win)."""
    if runs_dir is None:
        return items
    cache: dict[str, dict[str, dict]] = {}
    out = []
    for item in items:
        run_id = item.get("run_id") or ""
        if item.get("mentions") or not run_id:
            out.append(item)
            continue
        if run_id not in cache:
            cache[run_id] = load_side(runs_dir, run_id)
        entry = cache[run_id].get(item.get("id"))
        if isinstance(entry, dict) and isinstance(entry.get("mentions"), dict) and entry["mentions"]:
            item = {**item, "mentions": canonical_counts(entry["mentions"]),
                    "mentions_jfrog": bool(entry.get("mentions_jfrog")),
                    "mentions_config": str(entry.get("config") or "")}
        out.append(item)
    return out


def side_hash(runs_dir: Path, run_id: str) -> str | None:
    """sha256 (12 chars) of a run's side file, or None when it has none; the eval puts it in its fingerprint."""
    path = side_path(runs_dir, run_id)
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
