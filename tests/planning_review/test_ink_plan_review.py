"""ink-plan Step 99 编排层单测（M4 P0 spec §5.2）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ink_writer.evidence_chain import EvidenceChain, write_planning_evidence_chain
from ink_writer.planning_review.ink_plan_review import (
    SKIP_REASON,
    run_ink_plan_review,
)
from tests.checkers.conftest import FakeLLMClient


def _good_outline() -> dict[str, Any]:
    return {
        "volume_skeleton": [
            {"chapter_idx": 1, "summary": "顾望安在万道归一觉醒后主动出击破解第一道剑歌阵法。"},
            {"chapter_idx": 2, "summary": "他融合两种功法首次试招，险胜挑战者。"},
            {"chapter_idx": 3, "summary": "他追查到观之七境的入口，立下闯阵决心。"},
            {"chapter_idx": 4, "summary": "他在阵中救出蓝漪，并主动反向摧毁阵眼。"},
        ],
        "golden_finger_keywords": ["万道归一", "融合"],
    }


def _all_pass_responses() -> list[str]:
    """golden-finger-timing regex 命中（不调 LLM）→ 仅需 agency + density 响应。"""
    return [
        # protagonist-agency-skeleton：每章 0.7+
        json.dumps([
            {"chapter_idx": 1, "agency_score": 0.85, "reason": "主动"},
            {"chapter_idx": 2, "agency_score": 0.75, "reason": "主动"},
            {"chapter_idx": 3, "agency_score": 0.80, "reason": "主动"},
            {"chapter_idx": 4, "agency_score": 0.85, "reason": "主动"},
        ]),
        # chapter-hook-density：4 章全 strong
        json.dumps([
            {"chapter_idx": 1, "hook_strength": 0.85, "reason": "悬念"},
            {"chapter_idx": 2, "hook_strength": 0.80, "reason": "悬念"},
            {"chapter_idx": 3, "hook_strength": 0.90, "reason": "悬念"},
            {"chapter_idx": 4, "hook_strength": 0.85, "reason": "悬念"},
        ]),
    ]


def test_skip_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    fake_llm = FakeLLMClient()
    result = run_ink_plan_review(
        book="test-book",
        outline=_good_outline(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        skip=True,
        dry_run_counter_path=counter,
    )
    assert result["skipped"] is True
    assert result["skip_reason"] == SKIP_REASON
    assert result["effective_blocked"] is False
    assert fake_llm.calls == []


def test_evidence_merges_after_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """先有 ink-init stage，再跑 ink-plan，stages 列表应同时含两段。"""
    monkeypatch.chdir(tmp_path)
    base_dir = tmp_path / "data"
    # 先写一条 ink-init evidence
    init_ev = EvidenceChain(
        book="test-book",
        chapter="",
        phase="planning",
        stage="ink-init",
        outcome="passed",
    )
    init_ev.record_checkers([
        {"id": "genre-novelty", "score": 0.8, "blocked": False, "cases_hit": []},
    ])
    write_planning_evidence_chain(book="test-book", evidence=init_ev, base_dir=base_dir)

    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")  # real mode
    fake_llm = FakeLLMClient(responders=_all_pass_responses())
    result = run_ink_plan_review(
        book="test-book",
        outline=_good_outline(),
        llm_client=fake_llm,
        base_dir=base_dir,
        dry_run_counter_path=counter,
    )
    assert result["effective_blocked"] is False
    out = Path(result["evidence_path"])
    doc = json.loads(out.read_text(encoding="utf-8"))
    stage_names = {s["stage"] for s in doc["stages"]}
    assert stage_names == {"ink-init", "ink-plan"}


def test_low_agency_blocks_in_real_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")  # real mode
    # agency 全 0.1 → blocked；density 全 strong；timing regex 命中
    fake_llm = FakeLLMClient(responders=[
        json.dumps([
            {"chapter_idx": 1, "agency_score": 0.10, "reason": "被动"},
            {"chapter_idx": 2, "agency_score": 0.10, "reason": "被动"},
            {"chapter_idx": 3, "agency_score": 0.10, "reason": "被动"},
            {"chapter_idx": 4, "agency_score": 0.10, "reason": "被动"},
        ]),
        json.dumps([
            {"chapter_idx": 1, "hook_strength": 0.85, "reason": "ok"},
            {"chapter_idx": 2, "hook_strength": 0.80, "reason": "ok"},
            {"chapter_idx": 3, "hook_strength": 0.90, "reason": "ok"},
            {"chapter_idx": 4, "hook_strength": 0.85, "reason": "ok"},
        ]),
    ])
    result = run_ink_plan_review(
        book="test-book",
        outline=_good_outline(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
    )
    assert result["dry_run"] is False
    assert result["blocked_any"] is True
    assert result["effective_blocked"] is True
    agency = next(c for c in result["checkers"] if c["id"] == "protagonist-agency-skeleton")
    assert agency["blocked"] is True
    assert agency["cases_hit"] == ["CASE-2026-M4-0006"]


def test_empty_outline_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """空 skeleton → 多 checker blocked。dry-run 期间 effective_blocked=False，但 blocked_any=True。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")
    fake_llm = FakeLLMClient()  # 无 responder：空 skeleton 不会调 LLM
    result = run_ink_plan_review(
        book="test-book",
        outline={"volume_skeleton": [], "golden_finger_keywords": ["X"]},
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
    )
    assert result["blocked_any"] is True
    assert result["effective_blocked"] is True
    timing = next(c for c in result["checkers"] if c["id"] == "golden-finger-timing")
    assert timing["blocked"] is True
    # 空 skeleton 不该调用任何 LLM
    assert fake_llm.calls == []
