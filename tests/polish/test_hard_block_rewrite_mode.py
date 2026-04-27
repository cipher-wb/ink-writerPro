"""US-013: hard_block_rewrite_mode 测试。

验证:
  1. 三个 hard block gate 失败 → 触发全章重写
  2. 重写后复检通过 → hard_blocked=False
  3. 重写后仍失败 → hard_blocked=True, exit code 2
  4. 开关 prose_overhaul_enabled=false → 跳过
  5. max_hard_block_retries=0 → 直接标 hard_blocked
  6. 无 hard block gate 失败 → 不触发重写
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from ink_writer.checker_pipeline.hard_block_rewrite import (
    HardBlockResult,
    _HARD_BLOCK_GATES,
    _build_rewrite_prompt,
    _build_chapter_report,
    _collect_violations,
    run_hard_block_rewrite,
)


SAMPLE_CHAPTER = """
第一章 穿越

李明睁开眼睛，看着眼前陌生的房间。古朴的木梁，纸糊的窗棂，还有那股淡淡的檀香味，无不提醒着他一件事情——他已经不在原来的世界了。

"少爷，您醒了！"一个丫鬟模样的少女推门而入，脸上满是惊喜之色。她穿着一身青色的粗布衣裙，看起来约莫十五六岁年纪。

李明缓缓坐起身来，打量着四周的环境。他的脑海中浮现出这具身体的记忆片段——李府三公子，从小体弱多病，昨日不慎落水后便昏迷不醒。

正所谓福兮祸之所伏，祸兮福之所倚。这次落水虽然险些要了他的性命，却也让他得以穿越而来，占据了这具躯体。
""".strip()


class TestCollectViolations:
    def test_collects_failed_gates(self) -> None:
        gate_results = {
            "anti_detection": {"status": "failed", "score": 0.0, "error": "zero_tolerance hit"},
            "colloquial": {"status": "passed", "score": 1.0},
            "directness": {"status": "failed", "score": 0.5, "error": "D6 nesting too deep"},
            "reader_pull": {"status": "passed"},
        }
        violations = _collect_violations(gate_results)
        assert len(violations) == 2
        assert any("anti_detection" in v for v in violations)
        assert any("directness" in v for v in violations)

    def test_no_violations_when_all_passed(self) -> None:
        gate_results = {
            "anti_detection": {"status": "passed", "score": 1.0},
            "colloquial": {"status": "passed", "score": 1.0},
            "directness": {"status": "passed", "score": 1.0},
        }
        violations = _collect_violations(gate_results)
        assert len(violations) == 0


class TestBuildRewritePrompt:
    def test_prompt_contains_chapter_text(self) -> None:
        prompt = _build_rewrite_prompt(SAMPLE_CHAPTER, ["[anti_detection] fail"], 1)
        assert "李明" in prompt
        assert "违规清单" in prompt
        assert "重写要求" in prompt

    def test_prompt_contains_violations(self) -> None:
        violations = ["[anti_detection] em-dash found", "[colloquial] C1 too high"]
        prompt = _build_rewrite_prompt(SAMPLE_CHAPTER, violations, 5)
        assert "em-dash found" in prompt
        assert "C1 too high" in prompt


class TestBuildChapterReport:
    def test_report_contains_status(self) -> None:
        report = _build_chapter_report(42, ["[anti_detection] fail"], "rewritten text")
        assert "HARD_BLOCKED" in report
        assert "第42章" in report
        assert "rewritten text" in report


class TestRunHardBlockRewrite:
    """核心重写流程测试（使用 mock LLM 和 mock check）。"""

    def _mock_llm(self, prompt: str) -> str:
        """返回一个修改过的章节文本（模拟重写成功）。"""
        return SAMPLE_CHAPTER.replace("正所谓", "古人说").replace("\n\n", "\n")

    def _mock_llm_short(self, prompt: str) -> str:
        """返回过短文本（模拟重写失败）。"""
        return "太短了"

    def _mock_check_pass(self, text: str) -> dict:
        return {
            "anti_detection": (True, 1.0),
            "colloquial": (True, 1.0),
            "directness": (True, 1.0),
        }

    def _mock_check_fail(self, text: str) -> dict:
        return {
            "anti_detection": (True, 1.0),
            "colloquial": (False, 0.3),
            "directness": (True, 1.0),
        }

    def _failed_gate_results(self) -> dict:
        return {
            "anti_detection": {"status": "failed", "score": 0.0, "error": "zero_tolerance: em_dash"},
            "colloquial": {"status": "failed", "score": 0.3, "error": "severity=red"},
            "directness": {"status": "passed", "score": 1.0},
            "reader_pull": {"status": "passed", "score": 1.0},
        }

    def test_no_hard_block_gates_failed(self) -> None:
        """无 hard block gate 失败 → 不触发重写。"""
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results={"anti_detection": {"status": "passed"}, "colloquial": {"status": "passed"}, "directness": {"status": "passed"}},
            project_root="/tmp",
        )
        assert not result.hard_blocked
        assert result.retry_count == 0

    def test_rewrite_success_after_retry(self) -> None:
        """重写后复检通过 → hard_blocked=False。"""
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
            _mock_llm_rewrite=self._mock_llm,
            _mock_check_fn=self._mock_check_pass,
        )
        assert not result.hard_blocked
        assert result.rewritten_text
        assert result.retry_count == 1

    def test_rewrite_fails_after_retries(self) -> None:
        """重写后复检仍失败 + max_retries 用尽 → hard_blocked=True。"""
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
            _mock_llm_rewrite=self._mock_llm,
            _mock_check_fn=self._mock_check_fail,
        )
        assert result.hard_blocked
        assert result.retry_count == 1

    def test_short_rewrite_triggers_hard_block(self) -> None:
        """重写文本过短 → 直接 hard_blocked。"""
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
            _mock_llm_rewrite=self._mock_llm_short,
            _mock_check_fn=self._mock_check_pass,
        )
        assert result.hard_blocked

    @patch("ink_writer.checker_pipeline.hard_block_rewrite._is_prose_overhaul_enabled")
    def test_prose_overhaul_disabled_skips(self, mock_enabled) -> None:
        """prose_overhaul_enabled=false → 跳过重写。"""
        mock_enabled.return_value = False
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
        )
        assert not result.hard_blocked
        assert result.retry_count == 0

    @patch("ink_writer.checker_pipeline.hard_block_rewrite._load_max_hard_block_retries")
    def test_max_retries_zero_blocks_immediately(self, mock_load) -> None:
        """max_hard_block_retries=0 → 直接标 hard_blocked。"""
        mock_load.return_value = 0
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
        )
        assert result.hard_blocked
        assert result.retry_count == 0

    def test_rewritten_text_differs_from_original(self) -> None:
        """重写后文本应与原文不同。"""
        result = run_hard_block_rewrite(
            SAMPLE_CHAPTER, 1,
            gate_results=self._failed_gate_results(),
            project_root="/tmp",
            _mock_llm_rewrite=self._mock_llm,
            _mock_check_fn=self._mock_check_pass,
        )
        assert result.rewritten_text != result.original_text


class TestHardBlockResult:
    def test_to_dict(self) -> None:
        r = HardBlockResult(
            chapter_id=1, hard_blocked=True, retry_count=1,
            failure_gates=["colloquial"], error="test error",
        )
        d = r.to_dict()
        assert d["hard_blocked"] is True
        assert d["chapter_id"] == 1
        assert d["retry_count"] == 1
        assert "colloquial" in d["failure_gates"]
