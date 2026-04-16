"""Tests for voice fingerprint fix prompt builder."""

from __future__ import annotations

import pytest

from ink_writer.voice_fingerprint.fingerprint import (
    ChapterVoiceReport,
    VoiceFingerprint,
    VoiceViolation,
)
from ink_writer.voice_fingerprint.fix_prompt_builder import (
    VIOLATION_FIX_TEMPLATES,
    build_fix_prompt,
    normalize_checker_output,
)


def test_fix_templates_coverage():
    expected_ids = [
        "VOICE_FORBIDDEN_EXPRESSION",
        "VOICE_CATCHPHRASE_ABSENT",
        "VOICE_VOCAB_MISMATCH",
        "VOICE_INDISTINCT",
    ]
    for vid in expected_ids:
        assert vid in VIOLATION_FIX_TEMPLATES, f"Missing template for {vid}"


def test_build_fix_prompt_empty():
    report = ChapterVoiceReport(chapter_no=1, overall_score=100.0, passed=True)
    assert build_fix_prompt(report) == ""


def test_build_fix_prompt_with_violations():
    v1 = VoiceViolation(
        violation_id="VOICE_FORBIDDEN_EXPRESSION",
        severity="critical",
        entity_id="xiaoyan",
        entity_name="萧炎",
        description='角色「萧炎」使用了禁忌表达: 「在下」',
        suggestion="移除或替换",
        must_fix=True,
    )
    v2 = VoiceViolation(
        violation_id="VOICE_CATCHPHRASE_ABSENT",
        severity="medium",
        entity_id="xiaoyan",
        entity_name="萧炎",
        description="角色「萧炎」已连续5章未使用任何口头禅",
        suggestion="融入口头禅",
    )
    report = ChapterVoiceReport(
        chapter_no=10,
        overall_score=50.0,
        violations=[v1, v2],
        passed=False,
    )
    fp = VoiceFingerprint(
        entity_id="xiaoyan",
        catchphrases=["斗之力", "三十年河东"],
        vocabulary_level="粗犷",
        tone="倔强",
    )
    prompt = build_fix_prompt(report, fingerprints={"xiaoyan": ("萧炎", fp)})
    assert "语气指纹修复指令" in prompt
    assert "VOICE_FORBIDDEN_EXPRESSION" in prompt
    assert "VOICE_CATCHPHRASE_ABSENT" in prompt
    assert "粗犷" in prompt
    assert "倔强" in prompt


def test_build_fix_prompt_with_distinctiveness():
    v = VoiceViolation(
        violation_id="VOICE_INDISTINCT",
        severity="medium",
        entity_id="a+b",
        entity_name="张三+李四",
        description="风格过于相似",
        suggestion="增大差异",
    )
    report = ChapterVoiceReport(
        chapter_no=5,
        overall_score=70.0,
        distinctiveness_issues=[v],
        passed=True,
    )
    prompt = build_fix_prompt(report)
    assert "VOICE_INDISTINCT" in prompt
    assert "辨识度" in prompt


def test_normalize_checker_output_standard():
    raw = {
        "score": 75.0,
        "violations": [
            {"id": "V1", "severity": "high", "must_fix": True, "description": "test"},
        ],
        "fix_prompt": "修复指令",
    }
    result = normalize_checker_output(raw)
    assert result["score"] == 75.0
    assert len(result["violations"]) == 1
    assert result["violations"][0]["id"] == "V1"
    assert result["fix_prompt"] == "修复指令"


def test_normalize_checker_output_alternative_keys():
    raw = {
        "overall_score": "80",
        "violations": [{"violation_id": "V2", "severity": "medium"}],
    }
    result = normalize_checker_output(raw)
    assert result["score"] == 80.0
    assert result["violations"][0]["id"] == "V2"


def test_normalize_checker_output_empty():
    result = normalize_checker_output({})
    assert result["score"] == 0.0
    assert result["violations"] == []
    assert result["fix_prompt"] == ""


def test_normalize_checker_output_invalid_score():
    result = normalize_checker_output({"score": "not_a_number"})
    assert result["score"] == 0.0


def test_normalize_checker_output_invalid_violations():
    result = normalize_checker_output({"violations": "not_a_list"})
    assert result["violations"] == []
