"""US-023 (FIX-18 P5e): progressions 端到端集成测试。

场景：80 章 mock 项目，配角"王小明"立场跨章三段渐变
- ch10: 立场 陌生→盟友
- ch40: 立场 盟友→中立
- ch70: 立场 中立→敌人

链路验证（P5a → P5b → P5c → P5d 全栈）：
1. P5a：真实 IndexManager.save_progression_event 写入 3 条事件，覆盖 80 章窗口
2. P5b：模拟 data-agent 输出格式（每章一份 progression_events 数组），按章回放写入
3. P5c：在第 79 章前调用 build_progression_summary → 返回完整渐变切片
4. P5d：
   - 第 79 章正文与渐变一致（提到"敌人"）→ 跨章 OOC 检测器零违规
   - 伪造的第 80 章突然"忠诚"且未呼应"敌人"→ CROSS_CHAPTER_OOC critical

零回归：本测试只读真实 IndexManager API，不改任何已有模块行为。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.progression import (
    build_progression_summary,
    render_progression_summary_md,
)

# 内联 P5d 等价检测器（与 tests/harness/test_ooc_checker_progression.py 同源逻辑）
# 不跨包 import，避免 sys.path 抖动；规格在 ink-writer/agents/ooc-checker.md Layer K
def detect_cross_chapter_ooc(
    progression_summary: dict,
    prev_summary_text: str,
    current_text: str,
    current_chapter: int,
) -> dict:
    if not progression_summary:
        return {"checked_chars": [], "violations": [], "skipped": True}
    haystack = (prev_summary_text or "") + "\n" + (current_text or "")
    violations: list[dict] = []
    checked: list[str] = []
    for char_id, rows in progression_summary.items():
        checked.append(char_id)
        for row in rows:
            from_v = row.get("from_value") or ""
            to_v = row.get("to_value") or ""
            if not from_v or not to_v:
                continue
            if from_v in haystack and to_v not in haystack:
                severity = "critical"
                distance = current_chapter - int(row["chapter_no"])
                if 0 < distance < 3:
                    severity = "high"
                if row.get("dimension") == "情绪":
                    severity = {"critical": "medium", "high": "low"}.get(severity, severity)
                violations.append({
                    "rule": "CROSS_CHAPTER_OOC",
                    "severity": severity,
                    "character_id": char_id,
                    "dimension": row.get("dimension"),
                    "progression_at_chapter": row["chapter_no"],
                    "progression_from": from_v,
                    "progression_to": to_v,
                })
    return {"checked_chars": checked, "violations": violations, "skipped": False}


pytestmark = pytest.mark.integration


CHAR_ID = "char_wangxiaoming"
TOTAL_CHAPTERS = 80


# 模拟 data-agent (P5b) 在三章逐个产出的 progression_events 数组
DATA_AGENT_OUTPUT_BY_CHAPTER = {
    10: [
        {
            "character_id": CHAR_ID,
            "dimension": "立场",
            "from_value": "陌生",
            "to_value": "盟友",
            "cause": "主角救其性命",
        }
    ],
    40: [
        {
            "character_id": CHAR_ID,
            "dimension": "立场",
            "from_value": "盟友",
            "to_value": "中立",
            "cause": "理念分歧加剧",
        }
    ],
    70: [
        {
            "character_id": CHAR_ID,
            "dimension": "立场",
            "from_value": "中立",
            "to_value": "敌人",
            "cause": "门派被主角所灭",
        }
    ],
}


def _make_real_idx(tmp_path: Path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return IndexManager(cfg)


def _replay_data_agent_output(idx) -> None:
    """模拟 80 章逐章运行 data-agent：每章把 progression_events 写入 IndexManager。"""
    for chapter_no in range(1, TOTAL_CHAPTERS + 1):
        events = DATA_AGENT_OUTPUT_BY_CHAPTER.get(chapter_no, [])
        for ev in events:
            idx.save_progression_event({**ev, "chapter_no": chapter_no})


def test_progressions_e2e_ch79_consistent_no_violation(tmp_path: Path, monkeypatch):
    """ch79 正文呼应 ch70 to_value='敌人'，跨章 OOC 检测器不应误报。"""
    idx = _make_real_idx(tmp_path, monkeypatch)
    _replay_data_agent_output(idx)

    # 三条 progression 全部就位
    rows = idx.get_progressions_for_character(CHAR_ID)
    assert len(rows) == 3
    assert [r["chapter_no"] for r in rows] == [10, 40, 70]
    assert rows[-1]["to_value"] == "敌人"

    # P5c：context-agent 在写第 79 章前注入 progression summary
    summary = build_progression_summary(idx, [CHAR_ID], before_chapter=79)
    assert CHAR_ID in summary
    summary_rows = summary[CHAR_ID]
    assert len(summary_rows) == 3
    assert summary_rows[-1]["to_value"] == "敌人"

    # markdown 摘要可生成（writer-agent 会拿到完整 progression）
    md = render_progression_summary_md(summary)
    assert "### " + CHAR_ID in md
    assert "| 70 |" in md
    assert "敌人" in md

    # P5d：第 79 章正文与 progression 一致（明确提到 to_value='敌人'）
    prev_summary = "前章摘要：王小明已彻底站到主角对立面，视其为不共戴天的敌人。"
    chapter_79_text = "王小明冷冷盯着主角，敌意如刀。两人狭路相逢，敌人之名再无回旋。"

    out = detect_cross_chapter_ooc(
        progression_summary=summary,
        prev_summary_text=prev_summary,
        current_text=chapter_79_text,
        current_chapter=79,
    )
    assert out["skipped"] is False
    assert out["checked_chars"] == [CHAR_ID]
    assert out["violations"] == [], (
        f"ch79 正文与 progression 一致，不应触发 CROSS_CHAPTER_OOC，实得：{out['violations']}"
    )


def test_progressions_e2e_ch80_sudden_loyalty_triggers_critical(tmp_path: Path, monkeypatch):
    """伪造 ch80 让王小明突然'忠诚'回归盟友姿态，未呼应最新 to_value → critical OOC。"""
    idx = _make_real_idx(tmp_path, monkeypatch)
    _replay_data_agent_output(idx)

    # P5c：第 80 章上下文摘要
    summary = build_progression_summary(idx, [CHAR_ID], before_chapter=80)
    assert len(summary[CHAR_ID]) == 3

    # P5d：伪造第 80 章正文 — 让王小明突然"忠诚"，且文本中出现"盟友"（ch40 from_value）
    # 但既未呼应 ch40 to_value='中立'，也未呼应 ch70 to_value='敌人'
    prev_summary = "前章摘要：风波渐起，朝野暗流涌动。"
    chapter_80_text = (
        "王小明突然单膝跪地，神情恭敬，对主角宣誓忠诚。"
        "举手投足间俨然又是当年并肩作战的盟友。"
    )

    out = detect_cross_chapter_ooc(
        progression_summary=summary,
        prev_summary_text=prev_summary,
        current_text=chapter_80_text,
        current_chapter=80,
    )

    assert out["skipped"] is False
    # 至少 ch40 行必须命中：from='盟友' in haystack & to='中立' not in haystack
    assert len(out["violations"]) >= 1
    critical = [v for v in out["violations"] if v["severity"] == "critical"]
    assert critical, f"预期至少一条 critical 违规，实得：{out['violations']}"

    v = critical[0]
    assert v["rule"] == "CROSS_CHAPTER_OOC"
    assert v["character_id"] == CHAR_ID
    assert v["dimension"] == "立场"


def test_progressions_e2e_summary_excludes_current_chapter_rows(tmp_path: Path, monkeypatch):
    """before_chapter 严格小于：检查第 70 章前的摘要不应包含 ch70 那条。"""
    idx = _make_real_idx(tmp_path, monkeypatch)
    _replay_data_agent_output(idx)

    summary = build_progression_summary(idx, [CHAR_ID], before_chapter=70)
    rows = summary[CHAR_ID]
    assert [r["chapter_no"] for r in rows] == [10, 40]
    # 还未渐变到"敌人"
    assert all(r["to_value"] != "敌人" for r in rows)
