"""US-007: progression/context_injection SQL LIMIT 下推测试。

覆盖：
1. IndexManager.get_recent_progressions_for_character 语义：按 DESC 取 N 条后升序返回
2. idx_char_chapter 复合索引存在
3. build_progression_summary 走 SQL LIMIT 路径（hasattr 探测）
4. 真实场景 10K progressions / 1 万 rows，single char，build_progression_summary <100ms
5. 新旧路径语义等价（同源对照）
6. 未实现新方法的 source 依然走旧 Python 侧切片路径（零回归）
7. ORM 参数校验（before_chapter/limit 非法值 raise）
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from ink_writer.progression import (
    DEFAULT_MAX_ROWS_PER_CHAR,
    build_progression_summary,
)


def _make_idx(tmp_path, monkeypatch):
    # 注：不需要 pytest.importorskip("data_modules.index_manager") — 真正使用的是
    # ink_writer.core.index.index_manager，existing harness 测试里的 importorskip
    # 是遗留写法，会让本机跳过。US-007 的 perf 测试必须真实执行，不得 skip。
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return IndexManager(cfg)


def _bulk_insert_progressions(idx, char_id: str, n: int) -> None:
    """绕开 save_progression_event 单条 UPSERT 的开销，直接批量 INSERT。

    n 对应 1 万章，每章 1 dimension。测试独占临时 DB，无 WAL 竞争。
    """
    with sqlite3.connect(str(idx.config.index_db)) as conn:
        rows = [
            (char_id, ch, "dim_a", f"v{ch-1}", f"v{ch}", f"cause_{ch}")
            for ch in range(1, n + 1)
        ]
        conn.executemany(
            """INSERT INTO character_progressions
               (character_id, chapter_no, dimension, from_value, to_value, cause)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()


# --- 1. IndexManager 新方法行为 ---


def test_get_recent_returns_top_n_in_ascending_order(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=20)

    rows = idx.get_recent_progressions_for_character("char_hero", before_chapter=15, limit=5)

    assert len(rows) == 5
    # DESC LIMIT 5 → 14,13,12,11,10；反转 → 10..14 升序
    assert [r["chapter_no"] for r in rows] == [10, 11, 12, 13, 14]
    # 每行字段完整（context_injection compact_row 会拿 chapter_no/dimension/from/to/cause）
    assert {"character_id", "chapter_no", "dimension", "from_value", "to_value", "cause"} <= set(rows[-1].keys())


def test_get_recent_respects_before_chapter_strictly(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=10)

    # before=5 严格小于 → 仅 ch1..ch4 可选，limit=10 但只有 4 条
    rows = idx.get_recent_progressions_for_character("char_hero", before_chapter=5, limit=10)
    assert [r["chapter_no"] for r in rows] == [1, 2, 3, 4]


def test_get_recent_unknown_char_returns_empty(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=5)

    assert idx.get_recent_progressions_for_character("char_ghost", before_chapter=10, limit=5) == []


def test_get_recent_invalid_args_raise(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        idx.get_recent_progressions_for_character("c", before_chapter=0, limit=5)
    with pytest.raises(ValueError):
        idx.get_recent_progressions_for_character("c", before_chapter=10, limit=0)


# --- 2. 复合索引存在 ---


def test_composite_index_exists(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    with sqlite3.connect(str(idx.config.index_db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='character_progressions'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert "idx_char_chapter" in names


# --- 3. build_progression_summary 走 SQL LIMIT 路径 ---


def test_build_summary_uses_limit_pushdown_when_available(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=100)

    # Spy：记录 get_recent_progressions_for_character 是否被调用
    calls = {"recent": 0, "legacy": 0}
    orig_recent = idx.get_recent_progressions_for_character
    orig_legacy = idx.get_progressions_for_character

    def recent_spy(char_id, before_chapter, limit):
        calls["recent"] += 1
        return orig_recent(char_id, before_chapter=before_chapter, limit=limit)

    def legacy_spy(char_id, before_chapter=None):
        calls["legacy"] += 1
        return orig_legacy(char_id, before_chapter=before_chapter)

    idx.get_recent_progressions_for_character = recent_spy  # type: ignore[method-assign]
    idx.get_progressions_for_character = legacy_spy  # type: ignore[method-assign]

    summary = build_progression_summary(idx, ["char_hero"], before_chapter=50)

    assert calls["recent"] == 1
    assert calls["legacy"] == 0  # 新路径不 fallback
    assert len(summary["char_hero"]) == DEFAULT_MAX_ROWS_PER_CHAR
    # 最近 5 章 = 45,46,47,48,49
    assert [r["chapter_no"] for r in summary["char_hero"]] == [45, 46, 47, 48, 49]


# --- 4. 性能：10K rows / 1 char / 100ms 预算 ---


def test_build_summary_under_100ms_with_10k_rows(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=10_000)

    start = time.perf_counter()
    summary = build_progression_summary(idx, ["char_hero"], before_chapter=9_500)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(summary["char_hero"]) == DEFAULT_MAX_ROWS_PER_CHAR
    assert [r["chapter_no"] for r in summary["char_hero"]] == [9495, 9496, 9497, 9498, 9499]
    # PRD 验收：<100ms。真实机器上 LIMIT 下推稳定在个位 ms；留出 10x headroom 防抖动。
    assert elapsed_ms < 100, f"build_progression_summary took {elapsed_ms:.1f}ms (> 100ms budget)"


# --- 5. 新旧路径语义等价（200 章对照）---


def test_new_and_legacy_paths_are_semantically_equivalent(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    _bulk_insert_progressions(idx, "char_hero", n=200)

    summary_new = build_progression_summary(idx, ["char_hero"], before_chapter=150)

    # 强制走旧路径：用 proxy 屏蔽新方法
    class _LegacyOnly:
        def __init__(self, real):
            self._real = real

        def get_progressions_for_character(self, char_id, before_chapter=None):
            return self._real.get_progressions_for_character(char_id, before_chapter=before_chapter)

    summary_legacy = build_progression_summary(
        _LegacyOnly(idx), ["char_hero"], before_chapter=150
    )

    assert summary_new == summary_legacy


# --- 6. 零回归：不实现新方法的 source 依然通过 ---


class _LegacyFakeSource:
    def __init__(self, events):
        self._events = events

    def get_progressions_for_character(self, char_id, before_chapter=None):
        rows = [e for e in self._events if e["character_id"] == char_id]
        if before_chapter is not None:
            rows = [r for r in rows if r["chapter_no"] < int(before_chapter)]
        rows.sort(key=lambda r: (r["chapter_no"], r.get("dimension", "")))
        return rows


def test_legacy_protocol_source_still_works():
    events = [
        {"character_id": "c1", "chapter_no": ch, "dimension": "d", "from_value": "x", "to_value": "y", "cause": "z"}
        for ch in range(1, 21)
    ]
    src = _LegacyFakeSource(events)

    summary = build_progression_summary(src, ["c1"], before_chapter=15)

    # 不走 LIMIT 下推：Python 侧 tail 5 = [10,11,12,13,14]
    assert [r["chapter_no"] for r in summary["c1"]] == [10, 11, 12, 13, 14]


# --- 7. max_rows_per_char 默认仍为 5 ---


def test_default_max_rows_per_char_still_five():
    assert DEFAULT_MAX_ROWS_PER_CHAR == 5
