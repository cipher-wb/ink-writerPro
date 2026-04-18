"""v16 US-003：LLM checker 工厂的单元测试。

覆盖：
- 严格 JSON 解析（含码块容错）。
- 字段类型纠偏（score 裸字符串、violations 非列表、severity 非法值等）。
- Shadow-safe 降级：LLM 调用抛异常 / 输出非字符串 / 解析失败 / prompt 空。
- passed 字段缺失时由 violations 推断。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ink_writer.checker_pipeline.llm_checker_factory import (
    DEFAULT_CHECKER_MODEL,
    _parse_checker_response,
    _shadow_safe_default,
    make_llm_checker,
)


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text("你是测试 checker。严格 JSON 输出。", encoding="utf-8")
    return p


# ---------------- _parse_checker_response ----------------------------------


class TestParseCheckerResponse:
    def test_bare_json_parses(self) -> None:
        raw = '{"score": 87, "violations": [], "passed": true}'
        out = _parse_checker_response(raw, "reader_pull")
        assert out == {"score": 87.0, "violations": [], "passed": True}

    def test_json_in_markdown_fence(self) -> None:
        raw = '```json\n{"score": 50, "violations": [], "passed": false}\n```'
        out = _parse_checker_response(raw, "emotion")
        assert out["score"] == 50.0
        assert out["passed"] is False

    def test_json_with_leading_text(self) -> None:
        raw = '这是 checker 输出：{"score": 90, "violations": [], "passed": true}'
        out = _parse_checker_response(raw, "anti_detection")
        assert out["score"] == 90.0

    def test_violations_preserved(self) -> None:
        raw = json.dumps({
            "score": 40,
            "violations": [
                {"id": "ZT_TIME", "severity": "hard", "location": "首段", "description": "..."},
                {"id": "SOFT_X", "severity": "soft", "location": "中段", "description": "..."},
            ],
            "passed": False,
        })
        out = _parse_checker_response(raw, "anti_detection")
        assert len(out["violations"]) == 2
        assert out["violations"][0]["severity"] == "hard"
        assert out["violations"][1]["severity"] == "soft"

    def test_invalid_severity_downgraded_to_soft(self) -> None:
        raw = json.dumps({
            "score": 70,
            "violations": [{"id": "X", "severity": "critical", "description": "..."}],
            "passed": True,
        })
        out = _parse_checker_response(raw, "voice")
        assert out["violations"][0]["severity"] == "soft"

    def test_passed_inferred_from_hard_violations_when_missing(self) -> None:
        raw = json.dumps({
            "score": 30,
            "violations": [{"id": "X", "severity": "hard", "description": "..."}],
        })
        out = _parse_checker_response(raw, "reader_pull")
        assert out["passed"] is False

    def test_passed_inferred_as_true_when_no_hard_violations(self) -> None:
        raw = json.dumps({
            "score": 80,
            "violations": [{"id": "X", "severity": "soft", "description": "..."}],
        })
        out = _parse_checker_response(raw, "emotion")
        assert out["passed"] is True

    def test_score_clamped_to_0_100_range(self) -> None:
        raw = json.dumps({"score": 250, "violations": [], "passed": True})
        out = _parse_checker_response(raw, "emotion")
        assert out["score"] == 100.0

        raw_neg = json.dumps({"score": -30, "violations": [], "passed": True})
        out_neg = _parse_checker_response(raw_neg, "emotion")
        assert out_neg["score"] == 0.0

    def test_score_string_coerced(self) -> None:
        raw = '{"score": "72", "violations": [], "passed": true}'
        out = _parse_checker_response(raw, "emotion")
        assert out["score"] == 72.0

    def test_score_invalid_falls_back_to_full(self) -> None:
        raw = '{"score": "not-a-number", "violations": [], "passed": true}'
        out = _parse_checker_response(raw, "emotion")
        assert out["score"] == 100.0

    def test_score_0_to_1_float_auto_scaled_to_0_100(self) -> None:
        """LLM 误用 0–1 小数时自动放大到 0–100 量纲。"""
        raw = '{"score": 0.72, "violations": [], "passed": true}'
        out = _parse_checker_response(raw, "emotion")
        assert out["score"] == 72.0

        raw_1 = '{"score": 1.0, "violations": [], "passed": true}'
        out_1 = _parse_checker_response(raw_1, "emotion")
        assert out_1["score"] == 100.0

    def test_non_dict_json_returns_shadow_safe(self) -> None:
        raw = "[1,2,3]"
        out = _parse_checker_response(raw, "voice")
        assert out == _shadow_safe_default()

    def test_malformed_json_returns_shadow_safe(self) -> None:
        raw = "this is not json"
        out = _parse_checker_response(raw, "voice")
        assert out == _shadow_safe_default()

    def test_empty_response_returns_shadow_safe(self) -> None:
        out = _parse_checker_response("", "voice")
        assert out == _shadow_safe_default()

    def test_violations_with_non_dict_items_filtered(self) -> None:
        raw = json.dumps({
            "score": 50,
            "violations": [{"id": "A", "severity": "hard"}, "not-a-dict", None, 42],
            "passed": False,
        })
        out = _parse_checker_response(raw, "voice")
        assert len(out["violations"]) == 1
        assert out["violations"][0]["id"] == "A"


# ---------------- make_llm_checker factory ---------------------------------


class TestMakeLlmChecker:
    def test_checker_uses_injected_call_fn(self, prompt_file: Path) -> None:
        captured: dict[str, Any] = {}

        def fake_call(**kwargs: Any) -> str:
            captured.update(kwargs)
            return '{"score": 66, "violations": [], "passed": true}'

        checker = make_llm_checker("reader_pull", prompt_file, call_fn=fake_call)
        result = checker("本章正文 ...", 42)

        assert result == {"score": 66.0, "violations": [], "passed": True}
        assert captured["model"] == DEFAULT_CHECKER_MODEL
        assert captured["task_type"] == "checker"
        assert "测试 checker" in captured["system"]
        assert "[chapter_no] 42" in captured["user"]
        assert captured["timeout"] == 90.0

    def test_checker_shadow_safe_on_exception(self, prompt_file: Path) -> None:
        def boom(**kwargs: Any) -> str:
            raise TimeoutError("network dead")

        checker = make_llm_checker("emotion", prompt_file, call_fn=boom)
        result = checker("任何内容", 1)
        assert result == _shadow_safe_default()

    def test_checker_shadow_safe_on_non_string_return(self, prompt_file: Path) -> None:
        def returns_dict(**kwargs: Any) -> Any:
            return {"not": "a string"}

        checker = make_llm_checker("emotion", prompt_file, call_fn=returns_dict)
        result = checker("任何内容", 1)
        assert result == _shadow_safe_default()

    def test_checker_shadow_safe_on_empty_text(self, prompt_file: Path) -> None:
        def should_not_be_called(**kwargs: Any) -> str:
            raise AssertionError("空 text 不应触发 LLM 调用")

        checker = make_llm_checker("voice", prompt_file, call_fn=should_not_be_called)
        assert checker("", 1) == _shadow_safe_default()
        assert checker("   ", 1) == _shadow_safe_default()

    def test_checker_shadow_safe_on_missing_prompt(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "does-not-exist.md"

        def should_not_be_called(**kwargs: Any) -> str:
            raise AssertionError("空 prompt 不应触发 LLM 调用")

        checker = make_llm_checker("anti_detection", missing, call_fn=should_not_be_called)
        assert checker("有正文", 1) == _shadow_safe_default()

    def test_simplified_call_fn_signature_supported(
        self, prompt_file: Path
    ) -> None:
        """兼容只接受 (model, system, user) 的 mock（不含 timeout/task_type）。"""

        calls: list[dict] = []

        def simple_fn(model: str, system: str, user: str) -> str:
            calls.append({"model": model, "system": system, "user": user})
            return '{"score": 90, "violations": [], "passed": true}'

        checker = make_llm_checker("plotline", prompt_file, call_fn=simple_fn)
        result = checker("正文", 2)
        assert result["score"] == 90.0
        assert len(calls) == 1

    def test_checker_hard_violation_marks_failed(
        self, prompt_file: Path
    ) -> None:
        def fail_fn(**kwargs: Any) -> str:
            return json.dumps({
                "score": 30,
                "violations": [
                    {"id": "HARD_NO_HOOK", "severity": "hard", "description": "章末无钩子"}
                ],
                "passed": False,
            })

        checker = make_llm_checker("reader_pull", prompt_file, call_fn=fail_fn)
        result = checker("一整章内容...", 5)
        assert result["passed"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["severity"] == "hard"

    def test_checker_exposes_metadata_attrs(self, prompt_file: Path) -> None:
        checker = make_llm_checker("voice", prompt_file, call_fn=lambda **kw: "{}")
        assert checker.gate_name == "voice"  # type: ignore[attr-defined]
        assert checker.model == DEFAULT_CHECKER_MODEL  # type: ignore[attr-defined]
        assert "测试 checker" in checker.system_prompt  # type: ignore[attr-defined]
