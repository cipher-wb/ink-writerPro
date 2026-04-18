"""US-021 (FIX-18 P5c): context-agent 注入 progression summary 验证。

场景：一个 80 章连载中的配角，跨多章多维度演进。
验证：
1. build_progression_summary 过滤 before_chapter，裁剪 ≤5 行/角色（保留最近的）
2. render_progression_summary_md 产出的"本章之前摘要"块结构完整（可直接嵌入 task-book）
3. 空输入降级到占位符
4. 空角色列表 / 未命中角色返回 {}
5. 真实 IndexManager 走通，证明签名兼容（不只是 Protocol mock）
"""
from __future__ import annotations

import pytest

from ink_writer.progression import (
    DEFAULT_MAX_ROWS_PER_CHAR,
    build_progression_summary,
    render_progression_summary_md,
)


class _FakeSource:
    """模拟 IndexManager.get_progressions_for_character 的最小实现。"""

    def __init__(self, events):
        self._events = events

    def get_progressions_for_character(self, char_id, before_chapter=None):
        rows = [e for e in self._events if e["character_id"] == char_id]
        if before_chapter is not None:
            rows = [r for r in rows if r["chapter_no"] < int(before_chapter)]
        rows.sort(key=lambda r: (r["chapter_no"], r.get("dimension", "")))
        return rows


def _mock_supporting_char_events():
    """配角 char_lixue：跨 ch5~ch78 的 8 次演进，覆盖 4 维度。"""
    base = [
        (5, "境界", "炼气三层", "炼气五层", "突破"),
        (12, "关系", "陌生", "盟友", "共同渡劫"),
        (20, "立场", "中立", "亲主角", "被主角救"),
        (33, "情绪", "平静", "焦虑", "家人遇险"),
        (41, "境界", "炼气五层", "筑基初期", "丹药辅助"),
        (55, "知识", "不知阴谋", "知晓幕后", "截获密信"),
        (66, "目标", "寻解药", "复仇", "得知真相"),
        (78, "关系", "盟友", "未婚妻", "誓约成立"),
    ]
    return [
        {
            "character_id": "char_lixue",
            "chapter_no": ch,
            "dimension": dim,
            "from_value": fv,
            "to_value": tv,
            "cause": cause,
        }
        for ch, dim, fv, tv, cause in base
    ]


def test_build_summary_trims_to_max_rows_keeping_latest():
    src = _FakeSource(_mock_supporting_char_events())

    summary = build_progression_summary(
        src, ["char_lixue"], before_chapter=80, max_rows_per_char=DEFAULT_MAX_ROWS_PER_CHAR
    )

    assert "char_lixue" in summary
    rows = summary["char_lixue"]
    # 共 8 条 < 章 80，裁剪为最近 5 条
    assert len(rows) == 5
    # 保留的是最近 5 条：章节 ∈ {33, 41, 55, 66, 78}
    chapters = [r["chapter_no"] for r in rows]
    assert chapters == [33, 41, 55, 66, 78]
    # compact 字段齐全
    assert set(rows[-1].keys()) == {"chapter_no", "dimension", "from_value", "to_value", "cause"}
    assert rows[-1]["to_value"] == "未婚妻"


def test_before_chapter_filter_excludes_current_and_future():
    src = _FakeSource(_mock_supporting_char_events())

    summary = build_progression_summary(src, ["char_lixue"], before_chapter=41)

    rows = summary["char_lixue"]
    # before_chapter=41 → 严格小于，ch5/12/20/33 入选
    chapters = [r["chapter_no"] for r in rows]
    assert chapters == [5, 12, 20, 33]
    assert all(c < 41 for c in chapters)


def test_missing_character_is_skipped():
    src = _FakeSource(_mock_supporting_char_events())

    summary = build_progression_summary(src, ["char_lixue", "char_ghost"], before_chapter=80)

    assert list(summary.keys()) == ["char_lixue"]
    assert "char_ghost" not in summary


def test_empty_char_ids_returns_empty_dict():
    src = _FakeSource(_mock_supporting_char_events())
    assert build_progression_summary(src, [], before_chapter=80) == {}


def test_render_markdown_contains_table_and_rows():
    src = _FakeSource(_mock_supporting_char_events())
    summary = build_progression_summary(src, ["char_lixue"], before_chapter=80)

    md = render_progression_summary_md(summary)

    # 板块标题 + 角色块 + 表格结构
    assert "## 本章之前 · 角色演进摘要" in md
    assert "### char_lixue" in md
    assert "| 章节 | 维度 | 从 | 到 | 原因 |" in md
    # 5 条保留行数据都能在 md 中找到（章节锚点）
    for ch in (33, 41, 55, 66, 78):
        assert f"| {ch} |" in md
    # 裁掉的 ch5 不应出现
    assert "| 5 |" not in md


def test_render_empty_summary_outputs_placeholder():
    md = render_progression_summary_md({})
    assert "[本章之前无角色演进记录]" in md


def test_invalid_before_chapter_raises():
    src = _FakeSource([])
    with pytest.raises(ValueError):
        build_progression_summary(src, ["x"], before_chapter=0)


def test_invalid_max_rows_raises():
    src = _FakeSource([])
    with pytest.raises(ValueError):
        build_progression_summary(src, ["x"], before_chapter=10, max_rows_per_char=0)


# ---------------------------------------------------------------------------
# 真实 IndexManager 兼容性 —— 确保签名 drift 时最先报警
# ---------------------------------------------------------------------------
def _make_real_idx(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return IndexManager(cfg)


def test_integrates_with_real_index_manager(tmp_path, monkeypatch):
    idx = _make_real_idx(tmp_path, monkeypatch)
    # 写入 7 条跨章事件
    for ch, dim, fv, tv in [
        (5, "境界", "炼气三层", "炼气五层"),
        (12, "关系", "陌生", "盟友"),
        (20, "立场", "中立", "亲主角"),
        (33, "情绪", "平静", "焦虑"),
        (41, "境界", "炼气五层", "筑基初期"),
        (55, "知识", "不知", "知晓"),
        (78, "关系", "盟友", "未婚妻"),
    ]:
        idx.save_progression_event({
            "character_id": "char_lixue",
            "chapter_no": ch,
            "dimension": dim,
            "from_value": fv,
            "to_value": tv,
            "cause": "mock",
        })

    summary = build_progression_summary(idx, ["char_lixue"], before_chapter=80)
    rows = summary["char_lixue"]
    # 7 条全部 < 80，裁剪至 5 条最近
    assert len(rows) == 5
    assert [r["chapter_no"] for r in rows] == [20, 33, 41, 55, 78]

    md = render_progression_summary_md(summary)
    assert "### char_lixue" in md
    assert "| 78 |" in md
    assert "| 5 |" not in md  # 被裁
