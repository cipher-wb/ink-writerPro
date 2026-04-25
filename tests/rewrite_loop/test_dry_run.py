"""tests for ink_writer.rewrite_loop.dry_run（US-009）。"""

from __future__ import annotations

from pathlib import Path

from ink_writer.rewrite_loop.dry_run import (
    increment_dry_run_counter,
    is_dry_run,
    read_dry_run_counter,
)


def _cfg(*, enabled: bool, observation: int = 5, switch: bool = True) -> dict:
    return {
        "dry_run": {
            "enabled": enabled,
            "observation_chapters": observation,
            "switch_to_block_after": switch,
        }
    }


def test_dry_run_disabled_returns_false(tmp_path: Path) -> None:
    cfg = _cfg(enabled=False)
    assert is_dry_run(cfg, base_dir=tmp_path) is False
    assert read_dry_run_counter(base_dir=tmp_path) == 0


def test_dry_run_enabled_returns_true_until_threshold(tmp_path: Path) -> None:
    cfg = _cfg(enabled=True, observation=5, switch=True)

    # 起始 counter=0，观察期内应保持 dry-run。
    assert is_dry_run(cfg, base_dir=tmp_path) is True

    # 累计 5 章后应自动切真阻断。
    for expected in range(1, 6):
        assert increment_dry_run_counter(base_dir=tmp_path) == expected

    assert read_dry_run_counter(base_dir=tmp_path) == 5
    assert is_dry_run(cfg, base_dir=tmp_path) is False  # auto-switch 触发

    # 持久化文件实际写入 data 路径。
    counter_file = tmp_path / ".dry_run_counter"
    assert counter_file.exists()
    assert counter_file.read_text(encoding="utf-8").strip() == "5"


def test_dry_run_no_auto_switch(tmp_path: Path) -> None:
    cfg = _cfg(enabled=True, observation=5, switch=False)

    # 跨过 observation 仍然保持 dry-run（switch_to_block_after=False）。
    for _ in range(7):
        increment_dry_run_counter(base_dir=tmp_path)

    assert read_dry_run_counter(base_dir=tmp_path) == 7
    assert is_dry_run(cfg, base_dir=tmp_path) is True
