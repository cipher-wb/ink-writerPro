"""v16 US-004：polish_llm_fn 工厂的单元测试。

覆盖：
- 正常路径：call_fn 返回修复文本 → polish 返回该文本并写审计日志。
- TimeoutError 降级：返回原文 + 审计 outcome=timeout_passthrough。
- 通用 Exception 降级：返回原文 + outcome=error_passthrough。
- 空 fix_prompt / 空 chapter_text → 不调 LLM，原文透传。
- 非字符串返回 / 空字符串返回 → 降级。
- 字数偏离 [0.5x, 2.0x] 外 → 降级（防 LLM 擅自改写整章）。
- 审计日志文件路径 / 追加模式 / 目录自动创建。
- 简化 call_fn 签名（不含 timeout/task_type）兼容。
- DEFAULT model = claude-sonnet-4-6；timeout = 120s。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ink_writer.checker_pipeline.polish_llm_fn import (
    DEFAULT_POLISH_MODEL,
    DEFAULT_POLISH_TIMEOUT_S,
    make_llm_polish,
)


ORIGINAL_TEXT = "次日清晨，主角睁开眼。众所周知，这是重要的一天。" * 20
POLISHED_TEXT = "山风掠过屋檐，少年睁开眼。他知道今天不同于往常。" * 20


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


class TestMakeLlmPolish:
    def test_normal_path_returns_polished_text(self, project_root: Path) -> None:
        captured: dict[str, Any] = {}

        def fake(**kwargs: Any) -> str:
            captured.update(kwargs)
            return POLISHED_TEXT

        polish = make_llm_polish("reader_pull", project_root=project_root, call_fn=fake)
        out = polish(ORIGINAL_TEXT, "章末钩子无力", 42)

        assert out == POLISHED_TEXT
        assert captured["model"] == DEFAULT_POLISH_MODEL
        assert captured["task_type"] == "polish"
        assert captured["timeout"] == DEFAULT_POLISH_TIMEOUT_S
        # system 包含核心约束词
        assert "不得改变剧情事实" in captured["system"]
        assert "章末钩子无力" in captured["user"]

    def test_audit_log_written_on_success(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return POLISHED_TEXT

        polish = make_llm_polish("voice", project_root=project_root, call_fn=fake)
        polish(ORIGINAL_TEXT, "OOC 对白", 7)

        log_path = project_root / ".ink" / "reports" / "polish_ch0007_gate_voice.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "outcome: success" in content
        assert "OOC 对白" in content
        assert "chapter=7" in content

    def test_audit_log_appends_on_repeat(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return POLISHED_TEXT

        polish = make_llm_polish("emotion", project_root=project_root, call_fn=fake)
        polish(ORIGINAL_TEXT, "fix1", 3)
        polish(ORIGINAL_TEXT, "fix2", 3)

        log_path = project_root / ".ink" / "reports" / "polish_ch0003_gate_emotion.md"
        content = log_path.read_text(encoding="utf-8")
        assert content.count("## polish attempt") == 2
        assert "fix1" in content
        assert "fix2" in content

    def test_timeout_falls_back_to_original(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            raise TimeoutError("LLM timeout after 120s")

        polish = make_llm_polish(
            "anti_detection", project_root=project_root, call_fn=fake
        )
        out = polish(ORIGINAL_TEXT, "次日清晨开头", 1)
        assert out == ORIGINAL_TEXT

        log_path = (
            project_root / ".ink" / "reports"
            / "polish_ch0001_gate_anti_detection.md"
        )
        assert "timeout_passthrough" in log_path.read_text(encoding="utf-8")

    def test_generic_exception_falls_back_to_original(
        self, project_root: Path
    ) -> None:
        def fake(**kwargs: Any) -> str:
            raise RuntimeError("network explode")

        polish = make_llm_polish("reader_pull", project_root=project_root, call_fn=fake)
        out = polish(ORIGINAL_TEXT, "fix", 5)
        assert out == ORIGINAL_TEXT

        log_path = project_root / ".ink" / "reports" / "polish_ch0005_gate_reader_pull.md"
        assert "error_passthrough" in log_path.read_text(encoding="utf-8")

    def test_empty_fix_prompt_skips_llm(self, project_root: Path) -> None:
        def should_not_be_called(**kwargs: Any) -> str:
            raise AssertionError("空 fix 不应触发 LLM")

        polish = make_llm_polish(
            "emotion", project_root=project_root, call_fn=should_not_be_called
        )
        out = polish(ORIGINAL_TEXT, "", 10)
        assert out == ORIGINAL_TEXT

        log_path = project_root / ".ink" / "reports" / "polish_ch0010_gate_emotion.md"
        assert "skip_empty_fix" in log_path.read_text(encoding="utf-8")

    def test_empty_chapter_text_passthrough(self, project_root: Path) -> None:
        def should_not_be_called(**kwargs: Any) -> str:
            raise AssertionError("空 chapter 不应触发 LLM")

        polish = make_llm_polish(
            "voice", project_root=project_root, call_fn=should_not_be_called
        )
        assert polish("", "fix", 1) == ""
        assert polish("   \n  ", "fix", 1) == "   \n  "

    def test_non_string_return_falls_back(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> Any:
            return {"not": "a string"}

        polish = make_llm_polish("voice", project_root=project_root, call_fn=fake)
        out = polish(ORIGINAL_TEXT, "fix", 2)
        assert out == ORIGINAL_TEXT

    def test_empty_string_return_falls_back(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return "   \n   "

        polish = make_llm_polish("voice", project_root=project_root, call_fn=fake)
        assert polish(ORIGINAL_TEXT, "fix", 2) == ORIGINAL_TEXT

    def test_length_guard_rejects_too_short_output(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return "短。"  # 远低于 0.5x 原文

        polish = make_llm_polish(
            "anti_detection", project_root=project_root, call_fn=fake
        )
        out = polish(ORIGINAL_TEXT, "fix", 8)
        assert out == ORIGINAL_TEXT

        log_path = (
            project_root / ".ink" / "reports"
            / "polish_ch0008_gate_anti_detection.md"
        )
        assert "length_guard_passthrough" in log_path.read_text(encoding="utf-8")

    def test_length_guard_rejects_too_long_output(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return ORIGINAL_TEXT * 3  # > 2x 原文

        polish = make_llm_polish(
            "reader_pull", project_root=project_root, call_fn=fake
        )
        out = polish(ORIGINAL_TEXT, "fix", 9)
        assert out == ORIGINAL_TEXT

    def test_simplified_call_fn_signature_supported(
        self, project_root: Path
    ) -> None:
        calls: list[dict] = []

        def simple(model: str, system: str, user: str) -> str:
            calls.append({"model": model, "system": system, "user": user})
            return POLISHED_TEXT

        polish = make_llm_polish(
            "voice", project_root=project_root, call_fn=simple
        )
        out = polish(ORIGINAL_TEXT, "fix", 4)
        assert out == POLISHED_TEXT
        assert len(calls) == 1
        assert calls[0]["model"] == DEFAULT_POLISH_MODEL

    def test_no_project_root_skips_audit(self, tmp_path: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return POLISHED_TEXT

        polish = make_llm_polish("voice", project_root=None, call_fn=fake)
        out = polish(ORIGINAL_TEXT, "fix", 1)
        assert out == POLISHED_TEXT
        # 未指定 project_root → .ink/reports 不应被创建
        assert not (tmp_path / ".ink" / "reports").exists()

    def test_write_audit_false_skips_audit(self, project_root: Path) -> None:
        def fake(**kwargs: Any) -> str:
            return POLISHED_TEXT

        polish = make_llm_polish(
            "voice",
            project_root=project_root,
            call_fn=fake,
            write_audit=False,
        )
        polish(ORIGINAL_TEXT, "fix", 1)
        assert not (project_root / ".ink" / "reports").exists()

    def test_metadata_attrs_exposed(self, project_root: Path) -> None:
        polish = make_llm_polish(
            "emotion", project_root=project_root, call_fn=lambda **kw: POLISHED_TEXT
        )
        assert polish.gate_name == "emotion"  # type: ignore[attr-defined]
        assert polish.model == DEFAULT_POLISH_MODEL  # type: ignore[attr-defined]
