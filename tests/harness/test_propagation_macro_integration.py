"""US-016 (FIX-17 P4c): macro-review propagation 触发器集成测试。

mock 100 章迭代：
- 默认 interval=50 → 触发 2 次（ch=50, ch=100）
- INK_PROPAGATION_INTERVAL=30 → 触发 3 次（ch=30, 60, 90）
- 触发后 stderr 摘要 + propagation_debt.json 落盘
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ink_writer.propagation import (
    DEFAULT_INTERVAL,
    INTERVAL_ENV,
    get_interval,
    run_propagation,
    should_run,
)


def _drift_record(target_chapter: int) -> dict:
    return {
        "critical_issues": [
            {
                "type": "cross_chapter_conflict",
                "target_chapter": target_chapter,
                "severity": "high",
                "rule": "character.power_level",
                "suggested_fix": "在目标章补伏笔",
            }
        ]
    }


# --- should_run / get_interval ---


def test_default_interval_is_50():
    assert DEFAULT_INTERVAL == 50
    assert INTERVAL_ENV == "INK_PROPAGATION_INTERVAL"


def test_get_interval_default_when_unset():
    assert get_interval(env={}) == 50


@pytest.mark.parametrize("raw,expected", [("30", 30), ("100", 100), ("", 50), ("abc", 50), ("0", 50), ("-5", 50)])
def test_get_interval_parses_env(raw, expected):
    assert get_interval(env={INTERVAL_ENV: raw}) == expected


@pytest.mark.parametrize(
    "chapter,interval,expected",
    [
        (50, 50, True),
        (49, 50, False),
        (100, 50, True),
        (60, 30, True),
        (61, 30, False),
        (0, 50, False),
        (-1, 50, False),
    ],
)
def test_should_run_logic(chapter, interval, expected):
    assert should_run(chapter, interval=interval) is expected


def test_should_run_reads_env():
    assert should_run(30, env={INTERVAL_ENV: "30"}) is True
    assert should_run(30, env={}) is False


# --- 100 章迭代触发次数 ---


def _count_triggers(total_chapters: int, env: dict) -> int:
    return sum(1 for ch in range(1, total_chapters + 1) if should_run(ch, env=env))


def test_100_chapter_loop_default_triggers_twice():
    assert _count_triggers(100, env={}) == 2


def test_100_chapter_loop_env_30_triggers_three_times():
    assert _count_triggers(100, env={INTERVAL_ENV: "30"}) == 3


# --- run_propagation ---


def test_run_propagation_no_drifts_writes_summary_only(tmp_path: Path):
    stderr = io.StringIO()
    drifts = run_propagation(
        tmp_path,
        current_chapter=50,
        env={},
        records={},
        stderr=stderr,
    )
    assert drifts == []
    msg = stderr.getvalue()
    assert "Propagation: 0 drifts detected" in msg
    assert ".ink/propagation_debt.json" in msg.replace("\\", "/")
    # 无 drift 时不强制建文件
    assert not (tmp_path / ".ink" / "propagation_debt.json").exists()


def test_run_propagation_with_drifts_persists_file(tmp_path: Path):
    records = {49: _drift_record(target_chapter=20)}
    stderr = io.StringIO()
    drifts = run_propagation(
        tmp_path,
        current_chapter=50,
        env={},
        records=records,
        stderr=stderr,
    )
    assert len(drifts) == 1
    assert drifts[0].target_chapter == 20
    assert drifts[0].chapter_detected == 49

    debt_file = tmp_path / ".ink" / "propagation_debt.json"
    assert debt_file.exists()
    payload = json.loads(debt_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["target_chapter"] == 20

    msg = stderr.getvalue()
    assert "Propagation: 1 drifts detected" in msg


def test_run_propagation_simulated_100_chapter_run(tmp_path: Path):
    """模拟跑 100 章，记录每次触发返回的 drift 数量。"""
    records = {ch: _drift_record(target_chapter=max(1, ch - 5)) for ch in (49, 99)}

    triggered_counts = []
    for ch in range(1, 101):
        if not should_run(ch, env={}):
            continue
        stderr = io.StringIO()
        drifts = run_propagation(
            tmp_path,
            current_chapter=ch,
            env={},
            records=records,
            stderr=stderr,
        )
        triggered_counts.append(len(drifts))
        assert "Propagation:" in stderr.getvalue()

    assert len(triggered_counts) == 2  # ch=50, ch=100
    assert triggered_counts == [1, 1]

    # 两次都 upsert 到同一文件，items 累计 2 条
    debt_file = tmp_path / ".ink" / "propagation_debt.json"
    payload = json.loads(debt_file.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 2
