"""Shared fixtures for editor_wisdom tests.

Forces the SDK code path in llm_backend.call_llm so that tests mocking
`anthropic.Anthropic` keep working after the CLI-fallback refactor.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _force_sdk_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-dummy-key")
