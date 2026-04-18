"""v16 US-021：cache_metrics 采集与 batch_review 降级单元测试。

覆盖：
- ``CacheMetricsTracker.record`` 写入 SQLite，字段齐全。
- ``get_metrics`` / ``get_report`` 聚合正确；hit_rate / savings_pct 计算无零除。
- ``llm_backend._record_cache_metrics`` 在 SDK 分支调用成功后写入 tracker。
- ``batch_review``：
  - chapters <= threshold → 直接走 fallback
  - 无 ANTHROPIC_API_KEY → 降级到 fallback
  - SDK 支持 batches → 调用 create/retrieve/results 并返回聚合
  - SDK 旧版（batches 属性缺失）→ 降级
  - batch.retrieve 抛异常 → 降级
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ink_writer.core.infra import api_client
from ink_writer.core.infra.api_client import batch_review
from ink_writer.prompt_cache.metrics import CacheMetricsTracker


class TestCacheMetricsRecord:
    def test_record_writes_row(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        tracker = CacheMetricsTracker(db_path=db_path)
        tracker.record(
            agent="writer",
            model="claude-opus-4-7",
            response_usage={
                "input_tokens": 100,
                "output_tokens": 200,
                "cache_creation_input_tokens": 500,
                "cache_read_input_tokens": 0,
            },
            chapter=7,
        )
        metrics = tracker.get_metrics()
        assert metrics.total_calls == 1
        assert metrics.cache_creation_tokens == 500
        assert metrics.cache_read_tokens == 0

    def test_hit_rate_computation(self, tmp_path: Path) -> None:
        tracker = CacheMetricsTracker(db_path=tmp_path / "c.db")
        # 1 次 creation + 3 次 read → hit_rate = 3 / (1+3)
        tracker.record(
            "ag",
            "m",
            {
                "input_tokens": 1000,
                "output_tokens": 0,
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 0,
            },
        )
        for _ in range(3):
            tracker.record(
                "ag",
                "m",
                {
                    "input_tokens": 1000,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 1000,
                },
            )
        metrics = tracker.get_metrics()
        assert metrics.total_calls == 4
        assert metrics.cache_creation_tokens == 1000
        assert metrics.cache_read_tokens == 3000
        assert metrics.cache_hit_rate == pytest.approx(0.75)

    def test_hit_rate_zero_when_no_cache(self, tmp_path: Path) -> None:
        tracker = CacheMetricsTracker(db_path=tmp_path / "c.db")
        tracker.record(
            "ag",
            "m",
            {
                "input_tokens": 100,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        metrics = tracker.get_metrics()
        assert metrics.cache_hit_rate == 0.0  # 无零除异常
        assert metrics.token_savings_pct == 0.0

    def test_filter_by_agent(self, tmp_path: Path) -> None:
        tracker = CacheMetricsTracker(db_path=tmp_path / "c.db")
        tracker.record(
            "writer",
            "m",
            {
                "input_tokens": 100,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 50,
            },
        )
        tracker.record(
            "checker",
            "m",
            {
                "input_tokens": 100,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 80,
            },
        )
        writer_m = tracker.get_metrics(agent="writer")
        checker_m = tracker.get_metrics(agent="checker")
        assert writer_m.cache_read_tokens == 50
        assert checker_m.cache_read_tokens == 80

    def test_get_report_structure(self, tmp_path: Path) -> None:
        tracker = CacheMetricsTracker(db_path=tmp_path / "c.db")
        tracker.record(
            "writer",
            "m",
            {
                "input_tokens": 100,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 30,
            },
        )
        report = tracker.get_report(last_n=5)
        assert "overall" in report
        assert "per_agent" in report
        assert "writer" in report["per_agent"]


class TestLlmBackendRecordsCacheMetrics:
    def test_sdk_path_records_cache_metrics(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """SDK 分支成功返回后，_record_cache_metrics 会写 tracker。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        # 重定向 tracker 到 tmp_path
        db_path = tmp_path / "cm.db"

        class _FakeUsage:
            input_tokens = 100
            output_tokens = 50
            cache_creation_input_tokens = 300
            cache_read_input_tokens = 700

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]
        mock_response.usage = _FakeUsage()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        captured_records: list[dict[str, Any]] = []

        class _SpyTracker:
            def __init__(self) -> None:
                pass

            def record(self, **kwargs: Any) -> None:
                captured_records.append(kwargs)

        with patch("anthropic.Anthropic", return_value=mock_client), patch(
            "ink_writer.prompt_cache.metrics.CacheMetricsTracker", _SpyTracker
        ):
            from ink_writer.editor_wisdom.llm_backend import call_llm

            call_llm(
                model="claude-opus-4-7",
                system="sys",
                user="u",
                timeout=30.0,
                max_retries=0,
            )

        assert len(captured_records) == 1
        rec = captured_records[0]
        assert rec["agent"] == "llm_backend"
        assert rec["model"] == "claude-opus-4-7"
        assert rec["response_usage"]["cache_creation_input_tokens"] == 300
        assert rec["response_usage"]["cache_read_input_tokens"] == 700


class TestBatchReview:
    def test_small_batch_uses_fallback(self) -> None:
        called: dict[str, Any] = {}

        def fb(chs: list[int]) -> dict[int, Any]:
            called["args"] = chs
            return {c: f"reviewed-{c}" for c in chs}

        out = batch_review([1, 2, 3], threshold=10, fallback=fb)
        assert called["args"] == [1, 2, 3]
        assert out == {1: "reviewed-1", 2: "reviewed-2", 3: "reviewed-3"}

    def test_no_api_key_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        def fb(chs: list[int]) -> dict[int, Any]:
            return {c: "fb" for c in chs}

        chapters = list(range(1, 13))  # 12 > 10
        out = batch_review(
            chapters, threshold=10, fallback=fb, build_request=lambda c: {}
        )
        assert len(out) == 12
        assert all(v == "fb" for v in out.values())

    def test_sdk_batch_path_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """模拟 SDK 支持 batches：提交 → ended → results 回收。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        fake_batch = MagicMock()
        fake_batch.id = "batch_abc"

        fake_final = MagicMock()
        fake_final.processing_status = "ended"

        def _entry(ch: int) -> MagicMock:
            e = MagicMock()
            e.custom_id = f"chapter-{ch}"
            e.result = {"type": "succeeded", "text": f"r{ch}"}
            return e

        mock_batches_api = MagicMock()
        mock_batches_api.create.return_value = fake_batch
        mock_batches_api.retrieve.return_value = fake_final
        mock_batches_api.results.return_value = [_entry(c) for c in range(1, 13)]

        mock_client = MagicMock()
        mock_client.messages.batches = mock_batches_api

        def fb(chs: list[int]) -> dict[int, Any]:
            raise AssertionError("fallback should not be called on success path")

        with patch("anthropic.Anthropic", return_value=mock_client):
            out = batch_review(
                list(range(1, 13)),
                threshold=10,
                build_request=lambda ch: {"model": "claude-haiku-4-5", "user": "u"},
                fallback=fb,
            )

        assert mock_batches_api.create.called
        # 12 条请求都进了 create
        create_kwargs = mock_batches_api.create.call_args.kwargs
        assert len(create_kwargs["requests"]) == 12
        assert all("custom_id" in r for r in create_kwargs["requests"])
        assert len(out) == 12
        assert out[1]["text"] == "r1"

    def test_sdk_missing_batches_attr_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """旧 SDK 无 messages.batches → AttributeError → 降级。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        # 让 mock_client.messages 不含 batches 属性
        mock_messages = MagicMock(spec=[])  # spec=[] 禁用所有属性
        mock_client = MagicMock()
        mock_client.messages = mock_messages

        fb_called: dict[str, Any] = {}

        def fb(chs: list[int]) -> dict[int, Any]:
            fb_called["args"] = chs
            return {c: "fb" for c in chs}

        with patch("anthropic.Anthropic", return_value=mock_client):
            out = batch_review(
                list(range(1, 13)),
                threshold=10,
                build_request=lambda ch: {},
                fallback=fb,
            )

        assert fb_called["args"] == list(range(1, 13))
        assert len(out) == 12

    def test_batch_not_ended_triggers_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retrieve 返回 in_progress → RuntimeError → 降级。"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        fake_batch = MagicMock()
        fake_batch.id = "batch_xyz"

        fake_final = MagicMock()
        fake_final.processing_status = "in_progress"

        mock_batches_api = MagicMock()
        mock_batches_api.create.return_value = fake_batch
        mock_batches_api.retrieve.return_value = fake_final

        mock_client = MagicMock()
        mock_client.messages.batches = mock_batches_api

        def fb(chs: list[int]) -> dict[int, Any]:
            return {c: "fb" for c in chs}

        with patch("anthropic.Anthropic", return_value=mock_client):
            out = batch_review(
                list(range(1, 13)),
                threshold=10,
                build_request=lambda ch: {},
                fallback=fb,
            )

        assert all(v == "fb" for v in out.values())

    def test_empty_chapters_returns_empty(self) -> None:
        assert batch_review([], fallback=lambda _: {}) == {}

    def test_missing_fallback_below_threshold_raises(self) -> None:
        with pytest.raises(ValueError):
            batch_review([1, 2], threshold=10, fallback=None)
