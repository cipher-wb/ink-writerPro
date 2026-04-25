"""Shared fixtures for M3 章节级 checker 单元测试。

`mock_llm_client` 实现最小化的 anthropic-shape：
``client.messages.create(...).content[0].text`` 返回预设值或 callable 结果。
风格与 `tests/writer_self_check/conftest.py` 保持一致，便于跨 checker 复用。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class _FakeContent:
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeContent]


@dataclass
class _FakeMessages:
    """记录每次 create 的 kwargs；按 FIFO 返回 responder 列表里的内容。"""

    responders: list[Callable[..., str] | str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _idx: int = 0

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if not self.responders:
            raise RuntimeError("FakeLLMClient: no responder configured")
        idx = min(self._idx, len(self.responders) - 1)
        responder = self.responders[idx]
        self._idx += 1
        text = responder(**kwargs) if callable(responder) else responder
        return _FakeResponse(content=[_FakeContent(text=text)])


class FakeLLMClient:
    """轻量 stub，兼容 ``llm_client.messages.create(...).content[0].text``。"""

    def __init__(self, responders: list[Callable[..., str] | str] | None = None) -> None:
        self.messages = _FakeMessages(responders=list(responders or []))

    def queue(self, response: Callable[..., str] | str) -> None:
        self.messages.responders.append(response)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


@pytest.fixture
def mock_llm_client() -> FakeLLMClient:
    return FakeLLMClient()
