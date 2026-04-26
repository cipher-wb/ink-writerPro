"""US-002 — is_dry_run 不再用 base.name == 'data' 启发式推路径。

旧实现：``aggregate_dry_run_metrics`` 期待 ``base/data/<book>/chapters``，于是
``_observation_quality_passed`` 用 ``scan_base = base.parent if base.name == 'data' else base``
反推。base_dir 命名不是 'data' 时（例如 ``test_data/`` / ``runtime/`` / 任意 prod 路径），
``scan_base = base`` → aggregate 看 ``base/data/<book>/chapters`` 找不到 → 永远 0 →
永远停在 dry-run。本测试覆盖该 silent failure。
"""

from __future__ import annotations

import json
from pathlib import Path

from ink_writer.rewrite_loop.dry_run import (
    increment_dry_run_counter,
    is_dry_run,
)


def _seed_evidence(
    *, base_dir: Path, book: str, delivered: int, not_delivered: int
) -> None:
    chapters = base_dir / book / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    idx = 1
    for _ in range(delivered):
        path = chapters / f"Ch{idx:03d}.evidence.json"
        path.write_text(json.dumps({"outcome": "delivered"}), encoding="utf-8")
        idx += 1
    for _ in range(not_delivered):
        path = chapters / f"Ch{idx:03d}.evidence.json"
        path.write_text(
            json.dumps({"outcome": "needs_human_review"}), encoding="utf-8"
        )
        idx += 1


def _cfg(threshold: float) -> dict:
    return {
        "dry_run": {
            "enabled": True,
            "observation_chapters": 5,
            "switch_to_block_after": True,
            "success_criteria": {"delivered_rate_threshold": threshold},
        }
    }


def test_is_dry_run_robust_when_base_dir_not_named_data(tmp_path: Path) -> None:
    """base_dir 命名不是 'data' 时也要正确读 evidence —— 旧实现这里返 True（误判）。

    base_dir = tmp_path/test_data
    evidence at base_dir/<book>/chapters/  → delivered=4 / total=5 → 0.8 ≥ 0.8 → 切真
    """
    base = tmp_path / "test_data"
    base.mkdir()
    book = "test_book"

    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    _seed_evidence(base_dir=base, book=book, delivered=4, not_delivered=1)

    cfg = _cfg(threshold=0.8)
    # 4/5 = 0.8 ≥ 0.8 → 质量达标 → 切真阻断 → False
    assert is_dry_run(cfg, base_dir=base, book=book) is False


def test_is_dry_run_robust_below_threshold_with_unconventional_base(
    tmp_path: Path,
) -> None:
    """name != 'data' 且 delivered_rate < 阈值 → 保持 dry-run。"""
    base = tmp_path / "runtime"
    base.mkdir()
    book = "test_book"

    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    _seed_evidence(base_dir=base, book=book, delivered=3, not_delivered=2)

    cfg = _cfg(threshold=0.8)
    # 3/5 = 0.6 < 0.8 → 不达标 → 保持 dry-run → True
    assert is_dry_run(cfg, base_dir=base, book=book) is True
