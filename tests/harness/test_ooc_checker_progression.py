"""US-022 (FIX-18 P5d): ooc-checker 消费 progression 做跨章一致性审计。

ooc-checker 是 Markdown Skill agent（无 Python 实现），契约测试两层：
1. 规格层：ooc-checker.md 必须包含 Layer K、CROSS_CHAPTER_OOC、规则与降级条件
2. 数据层：用一份与 spec 等价的纯 Python 检测器对若干 mock 冲突案例断言判定结果
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OOC_SPEC = REPO_ROOT / "ink-writer" / "agents" / "ooc-checker.md"

ALLOWED_DIMENSIONS = {"立场", "关系", "境界", "知识", "情绪", "目标"}


# ───────────────────── 规格层断言 ─────────────────────

@pytest.fixture(scope="module")
def spec_text() -> str:
    assert OOC_SPEC.exists(), f"ooc-checker 规格缺失：{OOC_SPEC}"
    return OOC_SPEC.read_text(encoding="utf-8")


def test_spec_declares_layer_k_section(spec_text: str) -> None:
    assert "Layer K" in spec_text, "规格缺少 Layer K 段落标题"
    assert "跨章 Progression 一致性检查" in spec_text, "规格缺少 Layer K 中文标题"


def test_spec_declares_cross_chapter_ooc_rule(spec_text: str) -> None:
    assert "CROSS_CHAPTER_OOC" in spec_text, "规格未声明 CROSS_CHAPTER_OOC 规则名"
    assert "critical" in spec_text, "规格未声明 critical 严重度"
    assert "hard block" in spec_text, "规格未声明 hard block 处置"


def test_spec_declares_input_contract(spec_text: str) -> None:
    for token in ("progression_summary", "from_value", "to_value", "dimension"):
        assert token in spec_text, f"规格输入契约缺少 {token}"


def test_spec_declares_skip_on_empty_summary(spec_text: str) -> None:
    assert "skipped" in spec_text, "规格未声明 skipped 降级语义"


def test_spec_lists_six_dimensions(spec_text: str) -> None:
    for dim in ALLOWED_DIMENSIONS:
        assert dim in spec_text, f"规格未提到 dimension：{dim}"


# ───────────────────── 数据层断言（mock 检测器） ─────────────────────

def detect_cross_chapter_ooc(
    progression_summary: dict,
    prev_summary_text: str,
    current_text: str,
    current_chapter: int,
) -> dict:
    """规格等价的纯 Python 实现，用于守 spec → 实现可拼接性。

    规则：
      1. 若 from_value 出现在 prev/current 文本中且 to_value 未出现 → CROSS_CHAPTER_OOC
      2. 距离当前章 <3 章 → severity 下调一级
      3. dimension == 情绪 → critical→medium, high→low
    """
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
                # 距离降级
                distance = current_chapter - int(row["chapter_no"])
                if 0 < distance < 3:
                    severity = "high"
                # 情绪降级
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


def _row(ch, dim, fv, tv):
    return {
        "chapter_no": ch,
        "dimension": dim,
        "from_value": fv,
        "to_value": tv,
        "cause": "mock",
    }


def test_empty_summary_skips_layer():
    out = detect_cross_chapter_ooc({}, "正文", "本章", current_chapter=80)
    assert out["skipped"] is True
    assert out["violations"] == []


def test_relationship_rollback_critical():
    """progression: ch12 关系 陌生→盟友；ch80 摘要仍写'陌生'。"""
    summary = {"char_lixue": [_row(12, "关系", "陌生", "盟友")]}
    prev = "前章摘要：林天对李雪仍如陌生人般生疏。"
    curr = "本章正文：两人无言。"
    out = detect_cross_chapter_ooc(summary, prev, curr, current_chapter=80)
    assert out["skipped"] is False
    assert len(out["violations"]) == 1
    v = out["violations"][0]
    assert v["rule"] == "CROSS_CHAPTER_OOC"
    assert v["severity"] == "critical"
    assert v["character_id"] == "char_lixue"
    assert v["dimension"] == "关系"


def test_consistent_state_no_violation():
    """progression: ch12 关系 陌生→盟友；ch80 摘要呼应 to_value。"""
    summary = {"char_lixue": [_row(12, "关系", "陌生", "盟友")]}
    prev = "前章摘要：林天与李雪并肩而立，盟友默契初现。"
    out = detect_cross_chapter_ooc(summary, prev, "本章 to_value 也提到盟友。", current_chapter=80)
    assert out["violations"] == []


def test_realm_regression_critical():
    """境界 from→to 后摘要仍称呼旧境界 → critical。"""
    summary = {"xiaoyan": [_row(41, "境界", "斗者", "斗师")]}
    prev = "前章摘要：萧炎仍是斗者一阶，被嘲讽为废物。"
    out = detect_cross_chapter_ooc(summary, prev, "本章无相关。", current_chapter=80)
    assert len(out["violations"]) == 1
    assert out["violations"][0]["severity"] == "critical"
    assert out["violations"][0]["dimension"] == "境界"


def test_distance_under_3_downgrades_to_high():
    """ch78 progression，本章 ch79（距离 1）→ critical 降级为 high。"""
    summary = {"char_a": [_row(78, "立场", "中立", "亲主角")]}
    prev = "前章摘要：他依旧保持中立立场。"
    out = detect_cross_chapter_ooc(summary, prev, "无", current_chapter=79)
    assert out["violations"][0]["severity"] == "high"


def test_emotion_dim_downgrades_critical_to_medium():
    """情绪维度的回退 critical → medium。"""
    summary = {"char_b": [_row(33, "情绪", "平静", "焦虑")]}
    prev = "前章摘要：他依然保持着平静的神色。"
    out = detect_cross_chapter_ooc(summary, prev, "无", current_chapter=80)
    assert out["violations"][0]["severity"] == "medium"


def test_emotion_dim_within_3_chapters_downgrades_to_low():
    """情绪 + 距离<3 → critical → high → low。"""
    summary = {"char_b": [_row(78, "情绪", "平静", "焦虑")]}
    prev = "前章摘要：他依然保持着平静的神色。"
    out = detect_cross_chapter_ooc(summary, prev, "无", current_chapter=79)
    assert out["violations"][0]["severity"] == "low"


def test_missing_from_or_to_value_skipped():
    """字段不全的 row 不参与判定。"""
    summary = {"char_x": [{"chapter_no": 10, "dimension": "境界", "from_value": "", "to_value": "斗师"}]}
    out = detect_cross_chapter_ooc(summary, "随便写", "随便写", current_chapter=20)
    assert out["violations"] == []


def test_multiple_chars_independent():
    summary = {
        "char_a": [_row(12, "关系", "陌生", "盟友")],
        "char_b": [_row(20, "立场", "中立", "亲主角")],
    }
    prev = "char_a：盟友默契；char_b 摘要：他始终保持中立。"
    out = detect_cross_chapter_ooc(summary, prev, "无", current_chapter=80)
    # char_a 一致 (含'盟友'），char_b 回退（出现'中立'未出现'亲主角'）
    chars_with_violation = {v["character_id"] for v in out["violations"]}
    assert chars_with_violation == {"char_b"}


def test_to_value_present_anywhere_clears_violation():
    """current_text 中出现 to_value 即认为已对齐，避免误报。"""
    summary = {"char_a": [_row(12, "关系", "陌生", "盟友")]}
    prev = "前章摘要：仍生疏如陌生人。"
    curr = "本章：两人确认了盟友关系。"
    out = detect_cross_chapter_ooc(summary, prev, curr, current_chapter=80)
    assert out["violations"] == []
