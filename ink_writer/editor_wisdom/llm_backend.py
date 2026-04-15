"""LLM backend adapter.

Prefers Anthropic SDK when ANTHROPIC_API_KEY is set; otherwise falls back to
the `claude -p` CLI so Claude Code OAuth (subscription) sessions work.

Supports prompt caching via cache_control on stable system prompt segments.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional


def call_llm(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    *,
    use_cache: bool = True,
) -> str:
    """Call Claude and return the raw text response.

    When use_cache=True and using the SDK, the system prompt is tagged
    with cache_control for Anthropic prompt caching.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()
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

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_param,
            messages=[{"role": "user", "content": user}],
        )
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
        timeout=90,
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
