"""US-024: verify ink_writer/core/infra/api_client.py uses logging (not print).

Covers two signals:

1. No raw ``print(`` calls survive in ``api_client.py`` (retry / warmup /
   stats all went through ``logger``).
2. ``ModalAPIClient.warmup`` / ``print_stats`` emit on the module logger
   so caplog can capture them – no stdout pollution.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import pytest

import ink_writer.core.infra.api_client as api_client


API_CLIENT_PATH = Path(api_client.__file__)


def test_api_client_has_no_raw_print_calls() -> None:
    src = API_CLIENT_PATH.read_text(encoding="utf-8")
    # strip comments/strings is overkill here; the regex below avoids
    # matching words like "sprint" while still catching "print(" / "  print(".
    hits = [
        line
        for line in src.splitlines()
        if re.search(r"(?<!\w)print\s*\(", line)
    ]
    assert hits == [], (
        "api_client.py should route observability through logging, "
        f"found print calls: {hits}"
    )


def test_warmup_uses_logger(monkeypatch, caplog) -> None:
    """``warmup`` should warn via the module logger, not stdout."""

    class _StubClient:
        async def warmup(self) -> None:  # pragma: no cover - trivial
            return None

    client = api_client.ModalAPIClient.__new__(api_client.ModalAPIClient)
    client._embed_client = _StubClient()
    client._rerank_client = _StubClient()
    client._warmed_up = {"embed": False, "rerank": False}

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=api_client.__name__):
        asyncio.run(client.warmup())

    messages = [rec.message for rec in caplog.records if rec.name == api_client.__name__]
    assert any("WARMUP" in msg for msg in messages), messages
    assert any("ready" in msg for msg in messages), messages


def test_print_stats_uses_logger(caplog) -> None:
    """``print_stats`` must log, even though the method name is legacy."""

    class _Stats:
        def __init__(self) -> None:
            self.total_calls = 3
            self.total_time = 1.5
            self.errors = 0

    class _Inner:
        def __init__(self) -> None:
            self.stats = _Stats()

    client = api_client.ModalAPIClient.__new__(api_client.ModalAPIClient)
    client._embed_client = _Inner()
    client._rerank_client = _Inner()

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=api_client.__name__):
        client.print_stats()

    messages = [rec.message for rec in caplog.records if rec.name == api_client.__name__]
    assert any("API STATS" in msg for msg in messages), messages
    assert any("EMBED" in msg and "calls" in msg for msg in messages), messages
