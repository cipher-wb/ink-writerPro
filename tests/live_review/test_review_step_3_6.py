"""US-LR-012 Tests for ink-review Step 3.6 接入点 + SKILL.md 含 Step 3.6 段。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CHAPTER = FIXTURES_DIR / "sample_chapter_violating.txt"
MOCK_CHECKER_RESPONSE = FIXTURES_DIR / "mock_live_review_checker_response.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD_PATH = REPO_ROOT / "ink-writer" / "skills" / "ink-review" / "SKILL.md"
AGENT_SPEC_PATH = REPO_ROOT / "ink-writer" / "agents" / "live-review-checker.md"


@pytest.fixture
def chapter_text() -> str:
    return SAMPLE_CHAPTER.read_text(encoding="utf-8")


@pytest.fixture
def mock_response() -> dict:
    return json.loads(MOCK_CHECKER_RESPONSE.read_text(encoding="utf-8"))


@pytest.fixture
def enabled_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: true\ninject_into:\n  init: true\n  review: true\n",
        encoding="utf-8",
    )
    return cfg


def test_a_mock_checker_with_polish_triggers_polish_loop(
    chapter_text: str, mock_response: dict, enabled_config: Path
) -> None:
    """(a) mock checker 假定违反 + mock polish-agent → checker 调用 + violations 写入 + polish 触发。"""
    from ink_writer.live_review.review_injection import check_review

    polish_calls: list[tuple[str, list[dict], int]] = []

    def mock_polish(text: str, violations: list[dict], chapter_no: int) -> str:
        polish_calls.append((text, violations, chapter_no))
        return text + "\n[POLISHED]"

    out = check_review(
        chapter_text,
        chapter_no=2,
        genre_tags=["都市", "重生"],
        mock_response=mock_response,
        polish_fn=mock_polish,
        config_path=enabled_config,
    )
    # checker called once, score below threshold, polish triggered
    assert out["disabled"] is False
    assert out["score"] == 0.45
    assert out["passed"] is False
    assert len(out["violations"]) == 3
    assert out["polish_triggered"] is True
    assert len(polish_calls) == 1
    # violations passed to polish_fn for evidence_chain consumption
    text_arg, violations_arg, chapter_no_arg = polish_calls[0]
    assert chapter_no_arg == 2
    assert len(violations_arg) == 3
    for v in violations_arg:
        assert "case_id" in v
        assert "evidence_quote" in v


def test_b_inject_into_review_false_short_circuits(
    chapter_text: str, mock_response: dict, tmp_path: Path
) -> None:
    """(b) inject_into.review=false → Step 3.6 短路：0 checker 调用 + 0 polish 调用。"""
    from ink_writer.live_review.review_injection import check_review

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: true\ninject_into:\n  init: true\n  review: false\n",
        encoding="utf-8",
    )
    polish_calls: list = []

    def mock_polish(text: str, violations: list[dict], chapter_no: int) -> str:
        polish_calls.append((text, violations, chapter_no))
        return text

    out = check_review(
        chapter_text,
        chapter_no=2,
        genre_tags=["都市"],
        mock_response=mock_response,
        polish_fn=mock_polish,
        config_path=cfg,
    )
    assert out["disabled"] is True
    assert out["passed"] is True  # 短路视为通行
    assert out["polish_triggered"] is False
    assert len(polish_calls) == 0
    # mock_response should not be consumed when disabled
    assert out["score"] == 1.0
    assert out["violations"] == []


def test_c_chapter_no_le_3_uses_golden_three_threshold(
    chapter_text: str, mock_response: dict, enabled_config: Path
) -> None:
    """(c) chapter_no <= 3 用 golden_three_threshold 0.75。"""
    from ink_writer.live_review.review_injection import check_review

    out = check_review(
        chapter_text,
        chapter_no=1,
        genre_tags=["都市"],
        mock_response=mock_response,
        polish_fn=None,
        config_path=enabled_config,
    )
    assert out["threshold"] == 0.75


def test_d_chapter_no_gt_3_uses_hard_gate_threshold(
    chapter_text: str, mock_response: dict, enabled_config: Path
) -> None:
    """(d) chapter_no > 3 用 hard_gate_threshold 0.65。"""
    from ink_writer.live_review.review_injection import check_review

    out = check_review(
        chapter_text,
        chapter_no=10,
        genre_tags=["都市"],
        mock_response=mock_response,
        polish_fn=None,
        config_path=enabled_config,
    )
    assert out["threshold"] == 0.65


def test_pass_above_threshold_does_not_trigger_polish(
    chapter_text: str, enabled_config: Path
) -> None:
    """score 超阈值 → polish_fn 不调用。"""
    from ink_writer.live_review.review_injection import check_review

    high_mock = {
        "score": 0.85,
        "dimensions": {"opening": 0.9, "pacing": 0.8},
        "violations": [],
        "cases_hit": ["CASE-LR-2026-0010"],
    }
    polish_calls: list = []

    def mock_polish(*args) -> str:
        polish_calls.append(args)
        return ""

    out = check_review(
        chapter_text,
        chapter_no=5,
        genre_tags=["职业流"],
        mock_response=high_mock,
        polish_fn=mock_polish,
        config_path=enabled_config,
    )
    assert out["passed"] is True
    assert out["polish_triggered"] is False
    assert len(polish_calls) == 0


def test_skill_md_contains_step_3_6_section() -> None:
    """ink-review/SKILL.md 必须含 'Step 3.6' 段 + run_live_review_checker 引用 + inject_into 提示。"""
    text = SKILL_MD_PATH.read_text(encoding="utf-8")
    assert "Step 3.6" in text, "SKILL.md should declare Step 3.6"
    assert "live-review" in text or "live_review" in text
    assert "run_live_review_checker" in text or "check_review" in text
    assert "inject_into" in text
    assert "OR" in text or "并列" in text


def test_agent_spec_exists_and_has_required_sections() -> None:
    """live-review-checker.md agent spec 必须存在且含核心结构段。"""
    assert AGENT_SPEC_PATH.exists(), "live-review-checker.md missing"
    text = AGENT_SPEC_PATH.read_text(encoding="utf-8")
    assert "{{PROMPT_TEMPLATE:checker-input-rules.md}}" in text
    assert "live-review-checker" in text
    for section in ("Purpose", "Input", "Retrieval", "Scoring", "Output"):
        assert section in text, f"agent spec missing section header '{section}'"
