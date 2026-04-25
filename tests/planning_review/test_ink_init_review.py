"""ink-init Step 99 编排层单测（M4 P0 spec §5.1）。

LLM checker 用 FakeLLMClient 注入；naming-style 用 tmp 词典；阈值 yaml
直接读真 ``config/checker-thresholds.yaml`` 不 monkeypatch（M4 已落档）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ink_writer.planning_review.ink_init_review import (
    SKIP_REASON,
    run_ink_init_review,
)
from tests.checkers.conftest import FakeLLMClient

GOOD_DESCRIPTION = (
    "主角觉醒『万道归一』之力：可融合任意两种已掌握的功法生成第三种新功法，"
    "代价是融合后 24 小时内无法再次融合，失败则双双失效，每月限 3 次。"
)
GOOD_MOTIVE = (
    "战争遗孤亲眼目睹养母在烽火中自尽，誓要找出『观之七境』背后的真正主使，"
    "却又恐惧自己变成同样的怪物，每一步逼近真相都在质问自己。"
)


@pytest.fixture
def fake_blacklist(tmp_path: Path) -> Path:
    """clean 词典：让 naming-style 拿满分。"""
    bl = tmp_path / "llm_naming_blacklist.json"
    bl.write_text(
        json.dumps({
            "exact_blacklist": [],
            "char_patterns": {
                "first_char_overused": [],
                "second_char_overused": [],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return bl


def _setting(blacklist_path: Path) -> dict[str, Any]:
    return {
        "genre_tags": ["仙侠", "正剧"],
        "main_plot_one_liner": "战争遗孤追查万道归一真相，最终改写历史。",
        "golden_finger_description": GOOD_DESCRIPTION,
        "character_names": [{"role": "protagonist", "name": "顾望安"}],
        "protagonist_motive_description": GOOD_MOTIVE,
        "_blacklist_path": str(blacklist_path),  # 仅供 monkeypatch；checker 用默认
    }


def _all_pass_responses() -> list[str]:
    """4 个 LLM checker 的成功响应（genre / golden_finger_spec / protagonist_motive）。

    naming-style 不调 LLM。Top200 空 → genre-novelty 不调 LLM。
    """
    return [
        # golden-finger-spec：4 维 ≥ 0.8
        json.dumps({
            "clarity": 0.85,
            "falsifiability": 0.80,
            "boundary": 0.85,
            "growth_curve": 0.80,
            "notes": "规格清晰",
        }),
        # protagonist-motive：3 维 ≥ 0.75
        json.dumps({
            "resonance": 0.80,
            "specific_goal": 0.75,
            "inner_conflict": 0.85,
            "notes": "动机扎实",
        }),
    ]


def test_skip_flag(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """skip=True 仅写 skipped stage，不调任何 checker。"""
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient()
    setting = _setting(fake_blacklist)
    result = run_ink_init_review(
        book="test-book",
        setting=setting,
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        skip=True,
        dry_run_counter_path=tmp_path / ".counter",
        naming_blacklist_path=fake_blacklist,
    )
    assert result["skipped"] is True
    assert result["skip_reason"] == SKIP_REASON
    assert result["effective_blocked"] is False
    assert result["checkers"] == []
    assert fake_llm.calls == []
    out = Path(result["evidence_path"])
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["phase"] == "planning"
    assert any(s.get("stage") == "ink-init" for s in doc["stages"])


def test_dry_run_blocked_does_not_fail(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dry-run 期内即便 checker 阻断，effective_blocked=False。"""
    monkeypatch.chdir(tmp_path)
    # golden-finger-spec 全 0.1 → blocked
    fake_llm = FakeLLMClient(responders=[
        json.dumps({
            "clarity": 0.1,
            "falsifiability": 0.1,
            "boundary": 0.1,
            "growth_curve": 0.1,
            "notes": "模糊",
        }),
        json.dumps({
            "resonance": 0.85,
            "specific_goal": 0.80,
            "inner_conflict": 0.80,
            "notes": "ok",
        }),
    ])
    counter = tmp_path / ".counter"  # 起始 0 → dry_run=True
    setting = _setting(fake_blacklist)
    result = run_ink_init_review(
        book="test-book",
        setting=setting,
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    assert result["dry_run"] is True
    assert result["blocked_any"] is True
    assert result["effective_blocked"] is False
    # dry-run 跑后计数 +1
    assert counter.read_text(encoding="utf-8") == "1"


def test_real_mode_blocks_on_failure(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """计数已满 5 → real mode；任一 checker blocked → effective_blocked=True。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")  # observation 满 → real mode

    fake_llm = FakeLLMClient(responders=[
        # golden-finger-spec：均分 0.1 → blocked
        json.dumps({
            "clarity": 0.1,
            "falsifiability": 0.1,
            "boundary": 0.1,
            "growth_curve": 0.1,
            "notes": "模糊",
        }),
        json.dumps({
            "resonance": 0.85,
            "specific_goal": 0.80,
            "inner_conflict": 0.80,
            "notes": "ok",
        }),
    ])
    setting = _setting(fake_blacklist)
    result = run_ink_init_review(
        book="test-book",
        setting=setting,
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    assert result["dry_run"] is False
    assert result["blocked_any"] is True
    assert result["effective_blocked"] is True
    # blocked checker 注入 case_ids
    spec_outcome = next(c for c in result["checkers"] if c["id"] == "golden-finger-spec")
    assert spec_outcome["cases_hit"] == ["CASE-2026-M4-0002"]


def test_all_pass_real_mode(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """real mode 下 4 checker 全过 → effective_blocked=False。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")

    fake_llm = FakeLLMClient(responders=_all_pass_responses())
    setting = _setting(fake_blacklist)

    result = run_ink_init_review(
        book="test-book",
        setting=setting,
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    naming = next(c for c in result["checkers"] if c["id"] == "naming-style")
    spec = next(c for c in result["checkers"] if c["id"] == "golden-finger-spec")
    motive = next(c for c in result["checkers"] if c["id"] == "protagonist-motive")
    genre = next(c for c in result["checkers"] if c["id"] == "genre-novelty")

    assert spec["blocked"] is False
    assert motive["blocked"] is False
    # genre 走 empty top200 → score=1.0 / blocked=False
    assert genre["blocked"] is False
    assert naming["blocked"] is False
    assert result["dry_run"] is False
    assert result["blocked_any"] is False
    assert result["effective_blocked"] is False
    # real mode 不增计数
    assert counter.read_text(encoding="utf-8") == "5"


def test_evidence_chain_written(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evidence 文件必须落 phase=planning + stage=ink-init + checker_results 4 条。"""
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient(responders=_all_pass_responses())
    setting = _setting(fake_blacklist)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")

    result = run_ink_init_review(
        book="test-book",
        setting=setting,
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    out = Path(result["evidence_path"])
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["phase"] == "planning"
    assert doc["book"] == "test-book"
    init_stage = next(s for s in doc["stages"] if s["stage"] == "ink-init")
    checker_results = init_stage["phase_evidence"]["checkers"]
    ids = {c["id"] for c in checker_results}
    assert ids == {
        "genre-novelty",
        "golden-finger-spec",
        "naming-style",
        "protagonist-motive",
    }
