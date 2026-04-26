"""统一 LLM 客户端工厂 — env-driven 自动选 GLM (OpenAI 兼容) / anthropic SDK。

环境变量约定（与 ink_writer.meta_rule_emergence + scripts/corpus_chunking/cli.py 同款）：

- ``LLM_BASE_URL``（默认 ``https://open.bigmodel.cn/api/paas/v4``）
- ``LLM_API_KEY``（或 ``EMBED_API_KEY`` 作为 fallback）
- ``LLM_MODEL``（默认 ``glm-4.6``）

优先级：
1. ``LLM_API_KEY`` 设置 → ``LLMClient`` (OpenAI 兼容 → 智谱 GLM 等)
2. 否则 → ``anthropic.Anthropic()`` （需 ``ANTHROPIC_API_KEY``）

返回的 client 都暴露 ``messages.create(model=, max_tokens=, messages=)`` Anthropic-shaped API。
"""
from __future__ import annotations
import os
from typing import Any


def make_client(*, default_model: str = "claude-sonnet-4-6") -> tuple[Any, str]:
    """返回 ``(client, effective_model)``。

    Args:
        default_model: 仅在走 anthropic fallback 时生效；GLM 路径用
            ``LLM_MODEL`` 环境变量（默认 ``glm-4.6``）覆盖。

    Returns:
        ``(client, model_name)`` — ``client.messages.create()`` Anthropic-shaped API。

    Raises:
        RuntimeError: 既无 GLM key 也无 anthropic SDK 时抛错并指引设置方式。
    """
    glm_key = os.environ.get("LLM_API_KEY") or os.environ.get("EMBED_API_KEY")
    if glm_key:
        base_url = os.environ.get(
            "LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )
        model = os.environ.get("LLM_MODEL", "glm-4.6")
        from scripts.corpus_chunking.llm_client import LLMClient  # noqa: PLC0415

        return LLMClient(base_url=base_url, api_key=glm_key, default_model=model), model

    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Neither LLM_API_KEY (GLM) nor anthropic SDK available; "
            "set LLM_API_KEY for GLM (OpenAI-compat) or install anthropic + ANTHROPIC_API_KEY"
        ) from exc
    return anthropic.Anthropic(), default_model


__all__ = ["make_client"]
