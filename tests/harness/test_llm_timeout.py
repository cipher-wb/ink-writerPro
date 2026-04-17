"""US-012: LLM 调用 timeout 测试。

验证：
  1. 无 API_KEY 时 CLI 路径的 subprocess timeout 被尊重（mock 慢命令）
  2. SDK 路径的 anthropic APITimeoutError 被转成 TimeoutError
  3. 重试机制：2 次失败后 raise TimeoutError
"""
from __future__ import annotations

import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from ink_writer.editor_wisdom.llm_backend import (
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_LLM_RETRIES,
    call_llm,
)


def test_default_timeout_constant():
    assert DEFAULT_LLM_TIMEOUT_S == 60
    assert DEFAULT_LLM_RETRIES == 2


def test_cli_timeout_raises_timeouterror(monkeypatch):
    """CLI 分支的 subprocess.TimeoutExpired 转 TimeoutError + 重试后 raise。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    call_count = {"n": 0}

    def fake_run(*args, **kwargs):
        call_count["n"] += 1
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 60))

    monkeypatch.setattr(subprocess, "run", fake_run)

    # patch sleep to 0 for speed
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(TimeoutError, match="LLM CLI timeout"):
        call_llm("haiku", "sys", "user", max_retries=2, timeout=1)
    # 1 首次 + 2 重试 = 3 次
    assert call_count["n"] == 3


def test_sdk_timeout_raises_timeouterror(monkeypatch):
    """SDK 分支的 anthropic APITimeoutError（通过 name 匹配）转 TimeoutError。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(time, "sleep", lambda _: None)

    class FakeAPITimeoutError(Exception):
        pass

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = FakeAPITimeoutError("connection timeout")

    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        with pytest.raises(TimeoutError, match="LLM SDK timeout"):
            call_llm("haiku", "sys", "user", max_retries=1, timeout=1)
