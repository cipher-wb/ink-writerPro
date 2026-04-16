"""Tests for voice fingerprint OOC gate: retry loop, blocking, disabled mode."""

from __future__ import annotations

import os
import tempfile

import pytest

from ink_writer.voice_fingerprint.config import VoiceFingerprintConfig
from ink_writer.voice_fingerprint.ooc_gate import (
    VoiceGateAttempt,
    VoiceGateResult,
    run_voice_gate,
)


@pytest.fixture
def project_root():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_checker(score: float, violations: list[dict] | None = None):
    def checker_fn(text, chapter_no):
        return {
            "score": score,
            "violations": violations or [],
            "fix_prompt": "修复对话风格" if score < 60 else "",
        }
    return checker_fn


def _make_polish():
    calls = []
    def polish_fn(text, fix_prompt, chapter_no):
        calls.append({"text": text, "fix_prompt": fix_prompt, "chapter_no": chapter_no})
        return text + "\n[已润色]"
    polish_fn.calls = calls
    return polish_fn


def test_gate_disabled():
    config = VoiceFingerprintConfig(enabled=False)
    result = run_voice_gate(
        "test text", 1, "/tmp",
        checker_fn=_make_checker(0),
        polish_fn=_make_polish(),
        config=config,
    )
    assert result.passed is True
    assert result.final_score == 100.0
    assert result.final_text == "test text"


def test_gate_pass_first_attempt(project_root):
    config = VoiceFingerprintConfig(score_threshold=60.0)
    result = run_voice_gate(
        "good text", 1, project_root,
        checker_fn=_make_checker(85.0),
        polish_fn=_make_polish(),
        config=config,
    )
    assert result.passed is True
    assert result.final_score == 85.0
    assert len(result.attempts) == 1
    assert result.blocked_path is None


def test_gate_pass_after_retry(project_root):
    attempt_counter = {"count": 0}

    def checker_fn(text, chapter_no):
        attempt_counter["count"] += 1
        score = 40.0 if attempt_counter["count"] == 1 else 75.0
        return {
            "score": score,
            "violations": [{"id": "VOICE_FORBIDDEN_EXPRESSION", "severity": "critical"}] if score < 60 else [],
            "fix_prompt": "修复禁忌表达" if score < 60 else "",
        }

    polish = _make_polish()
    config = VoiceFingerprintConfig(score_threshold=60.0, max_retries=2)
    result = run_voice_gate(
        "bad text", 1, project_root,
        checker_fn=checker_fn,
        polish_fn=polish,
        config=config,
    )
    assert result.passed is True
    assert len(result.attempts) == 2
    assert result.attempts[0].passed is False
    assert result.attempts[1].passed is True
    assert len(polish.calls) == 1


def test_gate_blocked_after_max_retries(project_root):
    config = VoiceFingerprintConfig(score_threshold=60.0, max_retries=2)
    violations = [{"id": "VOICE_FORBIDDEN_EXPRESSION", "severity": "critical", "description": "禁忌表达", "entity_name": "萧炎"}]

    result = run_voice_gate(
        "bad text", 5, project_root,
        checker_fn=_make_checker(30.0, violations),
        polish_fn=_make_polish(),
        config=config,
    )
    assert result.passed is False
    assert result.final_score == 30.0
    assert len(result.attempts) == 2
    assert result.blocked_path is not None
    assert os.path.exists(result.blocked_path)
    assert result.final_text is None

    with open(result.blocked_path, encoding="utf-8") as f:
        content = f.read()
    assert "语气指纹门禁阻断" in content
    assert "VOICE_FORBIDDEN_EXPRESSION" in content


def test_gate_log_created(project_root):
    config = VoiceFingerprintConfig(score_threshold=60.0)
    run_voice_gate(
        "text", 3, project_root,
        checker_fn=_make_checker(80.0),
        polish_fn=_make_polish(),
        config=config,
    )
    log_path = os.path.join(project_root, "logs", "voice-fingerprint", "chapter_3.log")
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as f:
        log_content = f.read()
    assert "语气指纹门禁通过" in log_content


def test_gate_attempts_recorded(project_root):
    attempt_counter = {"count": 0}

    def checker_fn(text, chapter_no):
        attempt_counter["count"] += 1
        return {
            "score": 50.0,
            "violations": [{"id": "V1"}],
            "fix_prompt": "fix",
        }

    config = VoiceFingerprintConfig(score_threshold=60.0, max_retries=2)
    result = run_voice_gate(
        "text", 1, project_root,
        checker_fn=checker_fn,
        polish_fn=_make_polish(),
        config=config,
    )
    assert len(result.attempts) == 2
    for a in result.attempts:
        assert isinstance(a, VoiceGateAttempt)
        assert a.score == 50.0
        assert a.passed is False
