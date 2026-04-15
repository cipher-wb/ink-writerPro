"""LLM backend adapter.

Prefers Anthropic SDK when ANTHROPIC_API_KEY is set; otherwise falls back to
the `claude -p` CLI so Claude Code OAuth (subscription) sessions work.
"""
from __future__ import annotations

import os
import subprocess


def call_llm(model: str, system: str, user: str, max_tokens: int = 1024) -> str:
    """Call Claude and return the raw text response."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
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
