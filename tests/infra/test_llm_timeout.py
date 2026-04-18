"""v16 US-007：LLM 调用 timeout 行为单元测试。

覆盖：
- ``call_claude`` 默认 timeout 按 task_type 查表（writer/polish/checker/classify/extract）。
- 未知 task_type → 走 ``_FALLBACK_TIMEOUT`` = 120s。
- 显式传 ``timeout=`` 覆盖 task_type 默认。
- ``config/llm_timeouts.yaml`` 加载正确（首次调用后进入 _DEFAULT_TIMEOUTS_BY_TASK）。
- 底层 ``editor_wisdom.llm_backend.call_llm`` 抛 ``TimeoutError``，call_claude 透传异常
  （不自行吞掉，上层可决定降级）。
- ``client.messages.create`` 收到显式 ``timeout`` kwarg（AC #1 验证点）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ink_writer.core.infra import api_client
from ink_writer.core.infra.api_client import (
    _DEFAULT_TIMEOUTS_BY_TASK,
    _FALLBACK_TIMEOUT,
    call_claude,
)


class TestTimeoutDefaults:
    @pytest.fixture(autouse=True)
    def _reset_yaml_load_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 每个用例重置 _YAML_LOADED，以便 _load_yaml_timeouts_once 再读一次。
        monkeypatch.setattr(api_client, "_YAML_LOADED", False)

    def test_yaml_config_loaded_into_defaults(self) -> None:
        api_client._load_yaml_timeouts_once()
        # 与 config/llm_timeouts.yaml 对齐
        assert _DEFAULT_TIMEOUTS_BY_TASK["writer"] == 300.0
        assert _DEFAULT_TIMEOUTS_BY_TASK["polish"] == 180.0
        assert _DEFAULT_TIMEOUTS_BY_TASK["checker"] == 90.0
        assert _DEFAULT_TIMEOUTS_BY_TASK["classify"] == 60.0
        assert _DEFAULT_TIMEOUTS_BY_TASK["extract"] == 60.0

    def test_call_claude_uses_task_type_default_writer(self) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        with patch.object(
            api_client, "_load_yaml_timeouts_once", lambda: None
        ), patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                model="claude-haiku-4-5",
                system="sys",
                user="u",
                task_type="writer",
            )

        assert captured["timeout"] == _DEFAULT_TIMEOUTS_BY_TASK["writer"]

    def test_call_claude_unknown_task_falls_back_to_120(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(api_client, "_YAML_LOADED", True)  # 禁用 YAML 读取
        monkeypatch.setattr(api_client, "_FALLBACK_TIMEOUT", 120.0)
        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                model="claude-haiku-4-5",
                system="sys",
                user="u",
                task_type="mystery_task",  # 未知 task_type
            )

        assert captured["timeout"] == 120.0

    def test_explicit_timeout_overrides_task_default(self) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                model="claude-haiku-4-5",
                system="sys",
                user="u",
                task_type="writer",  # 默认 300
                timeout=45.0,  # 显式覆盖
            )
        assert captured["timeout"] == 45.0


class TestTimeoutExceptionsPropagate:
    def test_timeout_error_from_llm_backend_propagates(self) -> None:
        def fake_call_llm(**kwargs: Any) -> str:
            raise TimeoutError("LLM SDK timeout after 90s")

        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            with pytest.raises(TimeoutError):
                call_claude(
                    model="claude-haiku-4-5",
                    system="sys",
                    user="u",
                    task_type="checker",
                )

    def test_factory_consumers_graceful_degrade_on_timeout(
        self, tmp_path: Path
    ) -> None:
        """checker 工厂消费 TimeoutError 后降级为 shadow-safe pass（AC "异常被捕获 + 返回降级结果"）。"""
        from ink_writer.checker_pipeline.llm_checker_factory import (
            _shadow_safe_default,
            make_llm_checker,
        )

        def boom(**kwargs: Any) -> str:
            raise TimeoutError("boom")

        prompt = tmp_path / "p.md"
        prompt.write_text("严格 JSON 输出", encoding="utf-8")

        checker = make_llm_checker("checker", prompt, call_fn=boom)
        out = checker("一些正文...", 1)
        assert out == _shadow_safe_default()

    def test_polish_factory_timeout_returns_original_text(
        self, tmp_path: Path
    ) -> None:
        """polish 工厂消费 TimeoutError 后返回原文（AC "异常被捕获 + 返回降级结果"）。"""
        from ink_writer.checker_pipeline.polish_llm_fn import make_llm_polish

        def boom(**kwargs: Any) -> str:
            raise TimeoutError("boom")

        polish = make_llm_polish(
            "reader_pull", project_root=tmp_path, call_fn=boom
        )
        original = "原章节" * 50
        out = polish(original, "fix", 1)
        assert out == original


class TestExplicitTimeoutPassedToMessagesCreate:
    def test_messages_create_receives_explicit_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC #1：llm_backend._call_llm_once 给 client.messages.create() 显式传 timeout。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_response.usage = MagicMock()  # 避免 cache metrics 报错
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            from ink_writer.editor_wisdom.llm_backend import call_llm

            call_llm(
                model="claude-haiku-4-5",
                system="sys",
                user="u",
                timeout=77.0,
                max_retries=0,
            )

        kwargs = mock_client.messages.create.call_args.kwargs
        assert "timeout" in kwargs, "AC #1：messages.create 必须显式接收 timeout"
        assert kwargs["timeout"] == 77.0
