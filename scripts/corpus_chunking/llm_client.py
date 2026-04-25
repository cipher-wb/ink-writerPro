"""LLM client wrapper that mimics anthropic.Anthropic interface.

M2 (2026-04-24) 改造：scene_segmenter / chunk_tagger 写死调
``client.messages.create(model=, max_tokens=, messages=...)`` (anthropic 风格)，
但实际 ANTHROPIC_API_KEY 未配置；用户已有 ZhipuAI BigModel key (EMBED_API_KEY)。

本 wrapper 用 OpenAI-compatible client（智谱 BigModel 提供 OpenAI 兼容接口）
模拟 anthropic.Anthropic 的 ``messages.create`` 调用形态，让 segmenter/tagger
零改动即可切换 LLM provider。

响应字段映射：
  anthropic: ``resp.content[0].text``
  openai:    ``resp.choices[0].message.content``
本 wrapper 把 openai 响应包成 anthropic shape。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _AnthropicLikeMessage:
    text: str


@dataclass
class _AnthropicLikeResponse:
    content: list[_AnthropicLikeMessage]


class _AnthropicLikeMessagesAPI:
    """Mimics ``anthropic.Anthropic().messages`` namespace."""

    def __init__(self, openai_client: Any, default_model: str) -> None:
        self._oai = openai_client
        self._default_model = default_model
        self._last_call_at: float = 0.0  # for throttling

    def create(
        self,
        *,
        max_tokens: int,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.3,
    ) -> _AnthropicLikeResponse:
        """Call OpenAI-compatible chat completions with throttling + retry.

        Throttling: ZhipuAI GLM-5.1 限速 ~60 RPM；本 wrapper 强制每次调用前
        等待 ``min_interval`` 秒（默认 1.2s = 50 RPM safe margin），再加
        retry-on-429 退避（5 次：6/9/15/27/51s 指数退避）。
        """
        import time

        # Proactive throttling: 强制最小请求间隔
        min_interval = float(__import__("os").environ.get("LLM_MIN_INTERVAL", "1.2"))
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        max_retries = 5
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = self._oai.chat.completions.create(
                    model=model or self._default_model,
                    max_tokens=max_tokens,
                    messages=messages,
                    temperature=temperature,
                )
                self._last_call_at = time.monotonic()
                text = resp.choices[0].message.content or ""
                return _AnthropicLikeResponse(content=[_AnthropicLikeMessage(text=text)])
            except Exception as err:  # noqa: BLE001 — handle 429 generically
                last_err = err
                err_str = str(err)
                is_rate_limit = "429" in err_str or "rate" in err_str.lower() or "1302" in err_str
                if is_rate_limit and attempt < max_retries:
                    backoff = 6 + 3 * (2 ** attempt)  # 9, 12, 18, 30, 54
                    time.sleep(backoff)
                    continue
                if attempt < max_retries:  # 其他错误也尝试重试一次（短退避）
                    time.sleep(2)
                    continue
                raise
        if last_err:
            raise last_err
        raise RuntimeError("unreachable")


class LLMClient:
    """Anthropic-shaped wrapper over an OpenAI-compatible client.

    Args:
        base_url: e.g., ``"https://open.bigmodel.cn/api/paas/v4"`` (智谱)
        api_key: BigModel / OpenAI / DeepSeek 等兼容厂商的 key
        default_model: e.g., ``"glm-5.1"``

    Usage:
        >>> client = LLMClient(base_url=..., api_key=..., default_model="glm-5.1")
        >>> resp = client.messages.create(max_tokens=2048, messages=[{...}])
        >>> resp.content[0].text  # mimics anthropic shape
    """

    def __init__(self, *, base_url: str, api_key: str, default_model: str) -> None:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as err:  # pragma: no cover
            raise RuntimeError("openai package not installed") from err
        self._oai = OpenAI(base_url=base_url, api_key=api_key)
        self.messages = _AnthropicLikeMessagesAPI(self._oai, default_model)
