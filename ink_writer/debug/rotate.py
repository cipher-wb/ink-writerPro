"""JSONL rotation: cap single file size, gzip archive, prune old."""
from __future__ import annotations

import gzip
import shutil
from datetime import datetime, timezone
from pathlib import Path


def rotate_if_needed(
    events_path: Path,
    *,
    max_bytes: int,
    archive_keep: int,
) -> Path | None:
    """If events_path exceeds max_bytes, rotate to events.<UTCts>.jsonl.gz; prune old.

    Returns the archive Path, or None if no rotation occurred.
    """
    if not events_path.exists() or events_path.stat().st_size <= max_bytes:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive = events_path.parent / f"{events_path.stem}.{ts}{events_path.suffix}.gz"
    with events_path.open("rb") as src, gzip.open(archive, "wb") as dst:
        shutil.copyfileobj(src, dst)
    events_path.unlink()

    # Prune old archives, keeping newest archive_keep.
    pattern = f"{events_path.stem}.*{events_path.suffix}.gz"
    archives = sorted(events_path.parent.glob(pattern))
    while len(archives) > archive_keep:
        archives[0].unlink()
        archives.pop(0)

    return archive
