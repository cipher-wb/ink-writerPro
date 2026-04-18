"""v16 US-021：按 task_type 的模型自动选型单元测试。

覆盖：
- ``resolve_model(task_type)`` 返回 config/model_selection.yaml 中定义的模型。
- 显式 ``model=`` 优先于 task_type 查表结果。
- 未知 task_type → ``_FALLBACK_MODEL``。
- ``call_claude`` 未传 ``model`` 时按 task_type 自动选型，转发给底层 ``call_llm``。
- YAML 加载失败时仍能工作（走内置默认）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ink_writer.core.infra import api_client
from ink_writer.core.infra.api_client import (
    _DEFAULT_MODELS_BY_TASK,
    _FALLBACK_MODEL,
    call_claude,
    resolve_model,
)


class TestResolveModel:
    @pytest.fixture(autouse=True)
    def _reset_model_yaml_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 每个用例重置 _MODEL_YAML_LOADED，以便 _load_model_yaml_once 再读一次。
        monkeypatch.setattr(api_client, "_MODEL_YAML_LOADED", False)

    def test_yaml_loads_writer_to_opus(self) -> None:
        api_client._load_model_yaml_once()
        assert _DEFAULT_MODELS_BY_TASK["writer"] == "claude-opus-4-7"
        assert _DEFAULT_MODELS_BY_TASK["polish"] == "claude-opus-4-7"

    def test_yaml_loads_context_to_sonnet(self) -> None:
        api_client._load_model_yaml_once()
        assert _DEFAULT_MODELS_BY_TASK["context"] == "claude-sonnet-4-6"
        assert _DEFAULT_MODELS_BY_TASK["data"] == "claude-sonnet-4-6"

    def test_yaml_loads_checker_to_haiku(self) -> None:
        api_client._load_model_yaml_once()
        assert _DEFAULT_MODELS_BY_TASK["checker"] == "claude-haiku-4-5"
        assert _DEFAULT_MODELS_BY_TASK["classify"] == "claude-haiku-4-5"
        assert _DEFAULT_MODELS_BY_TASK["extract"] == "claude-haiku-4-5"

    def test_resolve_writer_returns_opus(self) -> None:
        assert resolve_model("writer") == "claude-opus-4-7"

    def test_resolve_checker_returns_haiku(self) -> None:
        assert resolve_model("checker") == "claude-haiku-4-5"

    def test_explicit_model_overrides_task_lookup(self) -> None:
        # 显式 model 非空字符串 → 直接返回，不查 YAML
        out = resolve_model("writer", model="claude-custom-xyz")
        assert out == "claude-custom-xyz"

    def test_empty_string_model_falls_back_to_task_lookup(self) -> None:
        # 空串被视为"未显式传"，走 task_type 查表
        out = resolve_model("writer", model="")
        assert out == "claude-opus-4-7"

    def test_unknown_task_type_returns_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api_client, "_MODEL_YAML_LOADED", True)  # 禁用重读
        monkeypatch.setattr(api_client, "_FALLBACK_MODEL", "claude-haiku-4-5")
        assert resolve_model("mystery_task") == "claude-haiku-4-5"


class TestCallClaudeAutoModelSelection:
    def test_call_claude_uses_writer_model_when_model_omitted(self) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                system="sys",
                user="u",
                task_type="writer",
            )

        assert captured["model"] == "claude-opus-4-7"

    def test_call_claude_uses_checker_model_when_model_omitted(self) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                system="sys",
                user="u",
                task_type="checker",
            )

        assert captured["model"] == "claude-haiku-4-5"

    def test_explicit_model_overrides_task_default(self) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                model="claude-custom-foo",
                system="sys",
                user="u",
                task_type="writer",  # 默认 opus
            )

        assert captured["model"] == "claude-custom-foo"

    def test_unknown_task_type_falls_back_to_fallback_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_call_llm(**kwargs: Any) -> str:
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(api_client, "_MODEL_YAML_LOADED", True)
        monkeypatch.setattr(api_client, "_FALLBACK_MODEL", "claude-haiku-4-5")
        with patch(
            "ink_writer.editor_wisdom.llm_backend.call_llm", side_effect=fake_call_llm
        ):
            call_claude(
                system="sys",
                user="u",
                task_type="mystery_task",
            )

        assert captured["model"] == "claude-haiku-4-5"


class TestYamlRobustness:
    def test_missing_yaml_file_uses_builtin_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # 指向不存在的 YAML 路径
        monkeypatch.setattr(api_client, "_MODEL_YAML_LOADED", False)
        monkeypatch.setattr(
            api_client, "_model_config_path", lambda: tmp_path / "nope.yaml"
        )
        api_client._load_model_yaml_once()
        # 内置默认仍有效
        assert _DEFAULT_MODELS_BY_TASK["writer"] == "claude-opus-4-7"

    def test_resolve_fallback_when_task_not_in_map(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api_client, "_MODEL_YAML_LOADED", True)
        monkeypatch.setattr(api_client, "_FALLBACK_MODEL", "fallback-model-id")
        out = resolve_model("not_a_real_task_type_12345")
        assert out == "fallback-model-id"
