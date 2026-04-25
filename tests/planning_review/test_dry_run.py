"""M4 planning_review.dry_run 计数器单测（spec §5.4）。"""

from __future__ import annotations

from pathlib import Path

from ink_writer.planning_review.dry_run import (
    get_counter,
    increment_counter,
    is_dry_run_active,
)


def test_counter_starts_at_zero(tmp_path: Path) -> None:
    counter = tmp_path / ".planning_dry_run_counter"
    assert get_counter(counter) == 0


def test_increment(tmp_path: Path) -> None:
    counter = tmp_path / ".planning_dry_run_counter"
    assert increment_counter(counter) == 1
    assert increment_counter(counter) == 2
    assert get_counter(counter) == 2
    assert counter.exists()


def test_dry_run_active_until_threshold(tmp_path: Path) -> None:
    counter = tmp_path / ".planning_dry_run_counter"
    assert is_dry_run_active(counter, observation_runs=3) is True
    increment_counter(counter)
    increment_counter(counter)
    assert is_dry_run_active(counter, observation_runs=3) is True
    increment_counter(counter)
    assert is_dry_run_active(counter, observation_runs=3) is False
