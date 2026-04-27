"""Integration tests for platform mode end-to-end.

Verifies that platform resolution flows correctly from state.json
through config loaders and checker adapters.
"""

import json
import tempfile
from pathlib import Path

import pytest


# ── helpers ──────────────────────────────────────────────


def _make_state_json(state_dir: Path, platform: str | None = None) -> dict:
    """Write a minimal state.json and return its content."""
    state = {
        "project_info": {
            "title": "测试作品",
            "genre": "玄幻",
            "target_chapters": 600,
            "target_words": 2_000_000,
        }
    }
    if platform is not None:
        state["project_info"]["platform"] = platform
        state["project_info"]["platform_label"] = {
            "qidian": "起点中文网",
            "fanqie": "番茄小说",
        }.get(platform, platform)

    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state


# ── platform resolution ──────────────────────────────────


def test_get_platform_returns_qidian_default():
    from ink_writer.platforms.resolver import get_platform

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        state_dir = root / ".ink"
        _make_state_json(state_dir, platform=None)
        assert get_platform(root) == "qidian"


def test_get_platform_returns_fanqie():
    from ink_writer.platforms.resolver import get_platform

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        state_dir = root / ".ink"
        _make_state_json(state_dir, platform="fanqie")
        assert get_platform(root) == "fanqie"


def test_get_platform_migrates_chinese_label():
    from ink_writer.platforms.resolver import get_platform

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        state_dir = root / ".ink"
        _make_state_json(state_dir, platform="起点")
        assert get_platform(root) == "qidian"


# ── platform-aware config loading ────────────────────────


def test_reader_pull_config_fanqie_tighter():
    from ink_writer.reader_pull.config import load_config

    cfg = load_config(platform="fanqie")
    assert cfg.score_threshold == 80.0
    assert cfg.golden_three_threshold == 85.0
    assert cfg.max_retries == 3


def test_reader_pull_config_qidian_default():
    from ink_writer.reader_pull.config import load_config

    cfg = load_config(platform="qidian")
    assert cfg.score_threshold == 70.0
    assert cfg.golden_three_threshold == 80.0
    assert cfg.max_retries == 2


def test_emotion_config_fanqie_tighter():
    from ink_writer.emotion.config import load_config

    cfg = load_config(platform="fanqie")
    assert cfg.variance_threshold == 0.10
    assert cfg.flat_segment_max == 1
    assert cfg.score_threshold == 70.0


def test_emotion_config_qidian_default():
    from ink_writer.emotion.config import load_config

    cfg = load_config(platform="qidian")
    assert cfg.variance_threshold == 0.15
    assert cfg.flat_segment_max == 2
    assert cfg.score_threshold == 60.0


# ── prose-impact weights ─────────────────────────────────


def test_prose_impact_weights_fanqie_action_heavy():
    from ink_writer.prose.directness_threshold_gates import get_prose_impact_weights

    w = get_prose_impact_weights("fanqie")
    assert w["verb_sharpness"] > w["lens_diversity"]
    assert w["verb_sharpness"] == 0.25
    assert w["lens_diversity"] == 0.10


def test_prose_impact_weights_qidian_balanced():
    from ink_writer.prose.directness_threshold_gates import get_prose_impact_weights

    w = get_prose_impact_weights("qidian")
    assert w["lens_diversity"] == 0.20
    assert w["verb_sharpness"] == 0.15


# ── anti-detection fanqie rules ───────────────────────────


def test_anti_detection_fanqie_extra_rules():
    from ink_writer.anti_detection.config import (
        FANQIE_EXTRA_RULES,
        get_zero_tolerance_rules,
        ZeroToleranceRule,
    )

    base = [ZeroToleranceRule(id="BASE-001", description="base rule", patterns=[r"\bAI\b"])]
    rules = get_zero_tolerance_rules("fanqie", base)
    assert len(rules) == 2
    assert any(r.id == "FQ-001" for r in rules)


def test_anti_detection_qidian_no_extra_rules():
    from ink_writer.anti_detection.config import (
        FANQIE_EXTRA_RULES,
        get_zero_tolerance_rules,
        ZeroToleranceRule,
    )

    base = [ZeroToleranceRule(id="BASE-001", description="base rule", patterns=[r"\bAI\b"])]
    rules = get_zero_tolerance_rules("qidian", base)
    assert len(rules) == 1
    assert not any(r.id == "FQ-001" for r in rules)


# ── thresholds loader platform-aware ─────────────────────


def test_thresholds_loader_fanqie():
    from ink_writer.checker_pipeline.thresholds_loader import load_thresholds_for_platform

    t = load_thresholds_for_platform("fanqie")
    assert t["high_point"]["block_threshold"] == 85
    assert t["colloquial"]["force_aggressive"] is True
    assert t["colloquial"]["block_threshold"] == 80


def test_thresholds_loader_qidian():
    from ink_writer.checker_pipeline.thresholds_loader import load_thresholds_for_platform

    t = load_thresholds_for_platform("qidian")
    assert t["high_point"]["block_threshold"] == 70
    assert "force_aggressive" not in t.get("colloquial", {})


# ── editor-wisdom fanqie categories ──────────────────────


def test_editor_wisdom_fanqie_categories():
    from ink_writer.editor_wisdom.context_injection import FANQIE_EDITOR_CATEGORIES

    assert "家庭伦理冲突" in FANQIE_EDITOR_CATEGORIES
    assert "打脸循环" in FANQIE_EDITOR_CATEGORIES
    assert "身份掉马" in FANQIE_EDITOR_CATEGORIES
    assert len(FANQIE_EDITOR_CATEGORIES) == 3
