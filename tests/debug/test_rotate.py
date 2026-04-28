"""Tests for JSONL rotation."""
from __future__ import annotations

from pathlib import Path

from ink_writer.debug.rotate import rotate_if_needed


def test_no_rotation_below_threshold(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_bytes(b"x" * 100)
    rotated = rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    assert rotated is None
    assert events.exists()


def test_rotates_above_threshold(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_bytes(b"x" * 2048)
    rotated = rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    assert rotated is not None
    assert rotated.suffix == ".gz"
    assert rotated.exists()
    # Original truncated / removed
    assert not events.exists() or events.stat().st_size == 0


def test_archive_keep_prunes_old(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    # Pre-create 6 archives with old timestamps
    for i in range(6):
        archive = tmp_path / f"events.2026010{i}T000000.jsonl.gz"
        archive.write_bytes(b"old")
    events.write_bytes(b"x" * 2048)
    rotate_if_needed(events, max_bytes=1024, archive_keep=5)
    archives = sorted(tmp_path.glob("events.*.jsonl.gz"))
    assert len(archives) == 5  # 6 old + 1 new - 2 oldest pruned = 5
