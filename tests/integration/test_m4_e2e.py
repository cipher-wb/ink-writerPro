"""M4 P0 上游策划层 e2e 集成测试（US-014, spec §10 验收清单）。

7 个用例覆盖 M4 P0 全链路：

1. ``test_thresholds_yaml_has_m4_sections`` — checker-thresholds.yaml 必含
   8 个 M4 section（7 checker + planning_dry_run）。
2. ``test_ink_init_e2e_success`` — ink-init 4 checker 串行 + 全过 + evidence
   写盘 + phase=planning + checker_results 4 条。
3. ``test_ink_plan_e2e_success`` — ink-plan 3 checker 串行 + 全过 + evidence
   stage=ink-plan + checker_results 3 条。
4. ``test_ink_init_then_ink_plan_merges`` — 同书先跑 ink-init 再跑 ink-plan，
   stages 合并为 {ink-init, ink-plan} + total_checkers == 7。
5. ``test_skip_flag_writes_evidence_with_skipped_true`` — skip=True 路径
   不调任何 LLM + 落 outcome=skipped + skipped 字段 True。
6. ``test_dry_run_counter_increments`` — dry-run 模式跑一次 ink-init，计数器
   +1 + effective_blocked 即便 blocked_any 也为 False。
7. ``test_seven_seed_cases_active`` — 7 个 CASE-2026-M4-0001~0007 全 active
   且 layer 含 upstream。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from ink_writer.case_library.store import CaseStore
from ink_writer.planning_review.ink_init_review import (
    SKIP_REASON,
    run_ink_init_review,
)
from ink_writer.planning_review.ink_plan_review import run_ink_plan_review
from tests.checkers.conftest import FakeLLMClient

GOOD_GOLDEN_FINGER = (
    "主角觉醒『万道归一』之力：可融合任意两种已掌握的功法生成第三种新功法，"
    "代价是融合后 24 小时内无法再次融合，失败则双双失效，每月限 3 次。"
)
GOOD_MOTIVE = (
    "战争遗孤亲眼目睹养母在烽火中自尽，誓要找出『观之七境』背后的真正主使，"
    "却又恐惧自己变成同样的怪物，每一步逼近真相都在质问自己。"
)


@pytest.fixture
def fake_blacklist(tmp_path: Path) -> Path:
    """clean 词典：让 naming-style 拿满分，避免依赖仓库 data/。"""
    bl = tmp_path / "llm_naming_blacklist.json"
    bl.write_text(
        json.dumps(
            {
                "exact_blacklist": [],
                "char_patterns": {
                    "first_char_overused": [],
                    "second_char_overused": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return bl


def _setting() -> dict[str, Any]:
    return {
        "genre_tags": ["仙侠", "正剧"],
        "main_plot_one_liner": "战争遗孤追查万道归一真相，最终改写历史。",
        "golden_finger_description": GOOD_GOLDEN_FINGER,
        "character_names": [{"role": "protagonist", "name": "顾望安"}],
        "protagonist_motive_description": GOOD_MOTIVE,
    }


def _outline() -> dict[str, Any]:
    return {
        "volume_skeleton": [
            {
                "chapter_idx": 1,
                "summary": "顾望安在万道归一觉醒后主动出击破解第一道剑歌阵法。",
            },
            {
                "chapter_idx": 2,
                "summary": "他融合两种功法首次试招，险胜挑战者。",
            },
            {
                "chapter_idx": 3,
                "summary": "他追查到观之七境的入口，立下闯阵决心。",
            },
            {
                "chapter_idx": 4,
                "summary": "他在阵中救出蓝漪，并主动反向摧毁阵眼。",
            },
        ],
        "golden_finger_keywords": ["万道归一", "融合"],
    }


def _ink_init_responses() -> list[str]:
    """ink-init 4 checker：top200 空 → genre 跳过 LLM；naming 纯规则；
    实际只调 golden-finger-spec + protagonist-motive 两次。"""
    return [
        json.dumps(
            {
                "clarity": 0.85,
                "falsifiability": 0.80,
                "boundary": 0.85,
                "growth_curve": 0.80,
                "notes": "规格清晰",
            }
        ),
        json.dumps(
            {
                "resonance": 0.80,
                "specific_goal": 0.75,
                "inner_conflict": 0.85,
                "notes": "动机扎实",
            }
        ),
    ]


def _ink_plan_responses() -> list[str]:
    """ink-plan 3 checker：timing regex 命中前 3 章 → 跳 LLM；
    agency + density 各调一次。"""
    return [
        json.dumps(
            [
                {"chapter_idx": 1, "agency_score": 0.85, "reason": "主动"},
                {"chapter_idx": 2, "agency_score": 0.75, "reason": "主动"},
                {"chapter_idx": 3, "agency_score": 0.80, "reason": "主动"},
                {"chapter_idx": 4, "agency_score": 0.85, "reason": "主动"},
            ]
        ),
        json.dumps(
            [
                {"chapter_idx": 1, "hook_strength": 0.85, "reason": "悬念"},
                {"chapter_idx": 2, "hook_strength": 0.80, "reason": "悬念"},
                {"chapter_idx": 3, "hook_strength": 0.90, "reason": "悬念"},
                {"chapter_idx": 4, "hook_strength": 0.85, "reason": "悬念"},
            ]
        ),
    ]


# ---------------------------------------------------------------------------
# 1) thresholds yaml
# ---------------------------------------------------------------------------


def test_thresholds_yaml_has_m4_sections() -> None:
    """config/checker-thresholds.yaml 必含 7 checker section + planning_dry_run。"""
    cfg_path = Path("config/checker-thresholds.yaml")
    assert cfg_path.exists(), f"missing {cfg_path}"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    required = {
        "genre_novelty",
        "golden_finger_spec",
        "naming_style",
        "protagonist_motive",
        "golden_finger_timing",
        "protagonist_agency_skeleton",
        "chapter_hook_density",
        "planning_dry_run",
    }
    missing = required - set(cfg.keys())
    assert not missing, f"missing thresholds sections: {missing}"
    # planning_dry_run 必含 observation_runs / counter_path
    pdr = cfg["planning_dry_run"]
    assert "observation_runs" in pdr
    assert "counter_path" in pdr


# ---------------------------------------------------------------------------
# 2) ink-init e2e success
# ---------------------------------------------------------------------------


def test_ink_init_e2e_success(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """real mode 下 4 checker 全过 + evidence 写盘 + phase=planning。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")  # observation 满 → real mode

    fake_llm = FakeLLMClient(responders=_ink_init_responses())
    result = run_ink_init_review(
        book="m4-e2e-book",
        setting=_setting(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    assert result["dry_run"] is False
    assert result["effective_blocked"] is False
    assert len(result["checkers"]) == 4
    ids = {c["id"] for c in result["checkers"]}
    assert ids == {
        "genre-novelty",
        "golden-finger-spec",
        "naming-style",
        "protagonist-motive",
    }

    out = Path(result["evidence_path"])
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["phase"] == "planning"
    init_stage = next(s for s in doc["stages"] if s["stage"] == "ink-init")
    assert len(init_stage["phase_evidence"]["checkers"]) == 4


# ---------------------------------------------------------------------------
# 3) ink-plan e2e success
# ---------------------------------------------------------------------------


def test_ink_plan_e2e_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """real mode 下 3 checker 全过 + evidence stage=ink-plan + 3 checkers。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")

    fake_llm = FakeLLMClient(responders=_ink_plan_responses())
    result = run_ink_plan_review(
        book="m4-e2e-book",
        outline=_outline(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
    )
    assert result["dry_run"] is False
    assert result["effective_blocked"] is False
    assert len(result["checkers"]) == 3
    ids = {c["id"] for c in result["checkers"]}
    assert ids == {
        "golden-finger-timing",
        "protagonist-agency-skeleton",
        "chapter-hook-density",
    }

    out = Path(result["evidence_path"])
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["phase"] == "planning"
    plan_stage = next(s for s in doc["stages"] if s["stage"] == "ink-plan")
    assert len(plan_stage["phase_evidence"]["checkers"]) == 3


# ---------------------------------------------------------------------------
# 4) ink-init then ink-plan merges
# ---------------------------------------------------------------------------


def test_ink_init_then_ink_plan_merges(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先 ink-init 再 ink-plan，evidence 含 2 stage + total_checkers == 7。"""
    monkeypatch.chdir(tmp_path)
    base_dir = tmp_path / "data"
    counter = tmp_path / ".counter"
    counter.write_text("5", encoding="utf-8")  # real mode

    init_llm = FakeLLMClient(responders=_ink_init_responses())
    init_result = run_ink_init_review(
        book="m4-merge-book",
        setting=_setting(),
        llm_client=init_llm,
        base_dir=base_dir,
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    assert init_result["effective_blocked"] is False

    plan_llm = FakeLLMClient(responders=_ink_plan_responses())
    plan_result = run_ink_plan_review(
        book="m4-merge-book",
        outline=_outline(),
        llm_client=plan_llm,
        base_dir=base_dir,
        dry_run_counter_path=counter,
    )
    assert plan_result["effective_blocked"] is False
    # ink-init 写完后 ink-plan 共享同一文件
    assert plan_result["evidence_path"] == init_result["evidence_path"]

    out = Path(plan_result["evidence_path"])
    doc = json.loads(out.read_text(encoding="utf-8"))
    stage_names = {s["stage"] for s in doc["stages"]}
    assert stage_names == {"ink-init", "ink-plan"}

    total_checkers = sum(
        len(s["phase_evidence"]["checkers"]) for s in doc["stages"]
    )
    assert total_checkers == 7  # 4 + 3


# ---------------------------------------------------------------------------
# 5) skip flag writes skipped evidence
# ---------------------------------------------------------------------------


def test_skip_flag_writes_evidence_with_skipped_true(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """skip=True：不调任何 LLM + 落 outcome=skipped + skipped True。"""
    monkeypatch.chdir(tmp_path)
    fake_llm = FakeLLMClient()
    result = run_ink_init_review(
        book="m4-skip-book",
        setting=_setting(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        skip=True,
        dry_run_counter_path=tmp_path / ".counter",
        naming_blacklist_path=fake_blacklist,
    )
    assert result["skipped"] is True
    assert result["skip_reason"] == SKIP_REASON
    assert fake_llm.calls == []
    out = Path(result["evidence_path"])
    doc = json.loads(out.read_text(encoding="utf-8"))
    init_stage = next(s for s in doc["stages"] if s["stage"] == "ink-init")
    assert init_stage["outcome"] == "skipped"


# ---------------------------------------------------------------------------
# 6) dry-run counter increments
# ---------------------------------------------------------------------------


def test_dry_run_counter_increments(
    tmp_path: Path,
    fake_blacklist: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dry-run 模式跑一次 ink-init，计数器 +1；blocked_any 时
    effective_blocked=False（dry-run 永不阻断）。"""
    monkeypatch.chdir(tmp_path)
    counter = tmp_path / ".counter"  # 起始 0 → dry-run

    # golden-finger-spec 全 0.1 → blocked
    fake_llm = FakeLLMClient(
        responders=[
            json.dumps(
                {
                    "clarity": 0.1,
                    "falsifiability": 0.1,
                    "boundary": 0.1,
                    "growth_curve": 0.1,
                    "notes": "模糊",
                }
            ),
            json.dumps(
                {
                    "resonance": 0.85,
                    "specific_goal": 0.80,
                    "inner_conflict": 0.80,
                    "notes": "ok",
                }
            ),
        ]
    )
    result = run_ink_init_review(
        book="m4-dryrun-book",
        setting=_setting(),
        llm_client=fake_llm,
        base_dir=tmp_path / "data",
        dry_run_counter_path=counter,
        naming_blacklist_path=fake_blacklist,
    )
    assert result["dry_run"] is True
    assert result["blocked_any"] is True
    assert result["effective_blocked"] is False
    assert counter.read_text(encoding="utf-8") == "1"


# ---------------------------------------------------------------------------
# 7) seven seed cases active
# ---------------------------------------------------------------------------


def test_seven_seed_cases_active() -> None:
    """7 个 CASE-2026-M4-0001~0007 全 active 且 layer 含 upstream。"""
    store = CaseStore(Path("data/case_library"))
    m4 = sorted(
        (c for c in store.iter_cases() if c.case_id.startswith("CASE-2026-M4")),
        key=lambda c: c.case_id,
    )
    assert len(m4) == 7
    expected_ids = {f"CASE-2026-M4-{i:04d}" for i in range(1, 8)}
    assert {c.case_id for c in m4} == expected_ids
    for case in m4:
        assert case.status.value == "active", (
            f"{case.case_id} status={case.status.value}"
        )
        layer_values = [layer.value for layer in case.layer]
        assert "upstream" in layer_values, (
            f"{case.case_id} layer missing upstream: {layer_values}"
        )
