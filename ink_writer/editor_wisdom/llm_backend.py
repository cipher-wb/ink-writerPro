"""LLM backend adapter.

Prefers Anthropic SDK when ANTHROPIC_API_KEY is set; otherwise falls back to
the `claude -p` CLI so Claude Code OAuth (subscription) sessions work.

Supports prompt caching via cache_control on stable system prompt segments.

v13 US-012：所有 LLM 调用都有显式 timeout（默认 60s）+ 最多 2 次重试（linear
backoff）。超时时抛 TimeoutError，上层可按需 catch。避免网络挂死导致全链路阻塞。
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Optional

# v13 US-012：LLM 超时与重试默认值
DEFAULT_LLM_TIMEOUT_S = 60  # 单次调用超时
DEFAULT_LLM_RETRIES = 2     # 超时后最多重试次数（不含首次）
LLM_BACKOFF_BASE_S = 2      # 线性退避基准秒数


def call_llm(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    *,
    use_cache: bool = True,
    timeout: float = DEFAULT_LLM_TIMEOUT_S,
    max_retries: int = DEFAULT_LLM_RETRIES,
) -> str:
    """Call Claude and return the raw text response.

    When use_cache=True and using the SDK, the system prompt is tagged
    with cache_control for Anthropic prompt caching.

    v13 US-012：timeout 默认 60s；超时或网络错误时最多重试 max_retries 次。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return _call_llm_once(
                model, system, user, max_tokens,
                use_cache=use_cache, timeout=timeout,
            )
        except TimeoutError as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(LLM_BACKOFF_BASE_S * (attempt + 1))
                continue
            raise
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(LLM_BACKOFF_BASE_S * (attempt + 1))
                continue
            # 转成 TimeoutError 让上层统一 catch
            raise TimeoutError(f"LLM CLI timeout after {timeout}s: {exc}") from exc
    # 理论上不应到达；保险起见 re-raise
    if last_exc:
        raise last_exc
    raise TimeoutError("LLM call exhausted retries without specific exception")


def _call_llm_once(
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    *,
    use_cache: bool,
    timeout: float,
) -> str:
    """单次 LLM 调用（SDK 或 CLI 分支）。timeout 传给对应路径。"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        # v13 US-012：给 SDK client 设超时（httpx 层）
        client = anthropic.Anthropic(timeout=timeout)
        system_param: Any
        if use_cache:
            system_param = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_param = system

        try:
            # v16 US-007：除 client 级 timeout 外，显式给 messages.create() 传 timeout，
            # 确保 per-request 级别也有硬约束（SDK 两层 timeout 取最短生效）。
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_param,
                messages=[{"role": "user", "content": user}],
                timeout=timeout,
            )
        except Exception as exc:
            # anthropic APITimeoutError 转 TimeoutError
            exc_name = type(exc).__name__
            if "Timeout" in exc_name or "timeout" in str(exc).lower():
                raise TimeoutError(f"LLM SDK timeout after {timeout}s: {exc}") from exc
            raise
        _record_cache_metrics(response, model, agent="llm_backend")
        return response.content[0].text

    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--no-session-persistence",
        "--append-system-prompt",
        system,
        user,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(timeout, 90),  # CLI 路径保底 90s 余量（启动慢）
        check=True,
    )
    return result.stdout


def _record_cache_metrics(
    response: Any, model: str, agent: str
) -> None:
    """Best-effort cache metrics recording."""
    try:
        usage = response.usage
        if not hasattr(usage, "cache_creation_input_tokens"):
            return
        from ink_writer.prompt_cache.metrics import CacheMetricsTracker

        tracker = CacheMetricsTracker()
        tracker.record(
            agent=agent,
            model=model,
            response_usage={
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cache_creation_input_tokens": getattr(
                    usage, "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": getattr(
                    usage, "cache_read_input_tokens", 0
                ),
            },
        )
    except Exception:
        pass
