"""Tests for prompt cache: config, segmenter, metrics tracker."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
import yaml

from ink_writer.prompt_cache.config import PromptCacheConfig, load_config
from ink_writer.prompt_cache.segmenter import (
    CacheableMessage,
    SegmentType,
    build_cached_system_param,
    estimate_tokens,
    segment_system_prompt,
)
from ink_writer.prompt_cache.metrics import CacheMetrics, CacheMetricsTracker


class TestPromptCacheConfig:
    def test_default_config(self):
        cfg = PromptCacheConfig()
        assert cfg.enabled is True
        assert cfg.min_cacheable_tokens == 1024
        assert "system_prompt" in cfg.stable_segments
        assert "chapter_outline" in cfg.volatile_segments

    def test_load_config_missing_file(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.enabled is True

    def test_load_config_from_file(self, tmp_path: Path):
        config_file = tmp_path / "prompt-cache.yaml"
        config_file.write_text(yaml.dump({
            "enabled": False,
            "min_cacheable_tokens": 2048,
            "stable_segments": ["a", "b"],
            "volatile_segments": ["c"],
        }))
        cfg = load_config(config_file)
        assert cfg.enabled is False
        assert cfg.min_cacheable_tokens == 2048
        assert cfg.stable_segments == ["a", "b"]

    def test_load_config_empty_file(self, tmp_path: Path):
        config_file = tmp_path / "prompt-cache.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.enabled is True


class TestCacheableMessage:
    def test_stable_block(self):
        msg = CacheableMessage(
            text="system prompt", segment_type=SegmentType.STABLE
        )
        block = msg.to_sdk_block()
        assert block["type"] == "text"
        assert block["text"] == "system prompt"
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_volatile_block(self):
        msg = CacheableMessage(
            text="chapter data", segment_type=SegmentType.VOLATILE
        )
        block = msg.to_sdk_block()
        assert block["type"] == "text"
        assert block["text"] == "chapter data"
        assert "cache_control" not in block


class TestSegmenter:
    def test_basic_segmentation(self):
        segments = segment_system_prompt("You are a writer.")
        assert len(segments) == 1
        assert segments[0].segment_type == SegmentType.STABLE
        assert segments[0].text == "You are a writer."

    def test_with_stable_prefix(self):
        segments = segment_system_prompt(
            "core prompt",
            stable_prefix="character archive",
        )
        assert len(segments) == 2
        assert segments[0].label == "stable_prefix"
        assert segments[1].label == "system_prompt"
        assert all(s.segment_type == SegmentType.STABLE for s in segments)

    def test_with_volatile_suffix(self):
        segments = segment_system_prompt(
            "core prompt",
            volatile_suffix="chapter 42 outline",
        )
        assert len(segments) == 2
        assert segments[0].segment_type == SegmentType.STABLE
        assert segments[1].segment_type == SegmentType.VOLATILE

    def test_full_segmentation(self):
        segments = segment_system_prompt(
            "core",
            stable_prefix="stable",
            volatile_suffix="volatile",
        )
        assert len(segments) == 3
        assert segments[0].segment_type == SegmentType.STABLE
        assert segments[1].segment_type == SegmentType.STABLE
        assert segments[2].segment_type == SegmentType.VOLATILE

    def test_empty_system_text(self):
        segments = segment_system_prompt("")
        assert len(segments) == 0

    def test_empty_prefix_suffix(self):
        segments = segment_system_prompt(
            "core", stable_prefix="", volatile_suffix=""
        )
        assert len(segments) == 1


class TestBuildCachedSystemParam:
    def test_with_cache(self):
        segments = [
            CacheableMessage("stable", SegmentType.STABLE),
            CacheableMessage("volatile", SegmentType.VOLATILE),
        ]
        result = build_cached_system_param(segments)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in result[1]

    def test_all_volatile(self):
        segments = [
            CacheableMessage("a", SegmentType.VOLATILE),
            CacheableMessage("b", SegmentType.VOLATILE),
        ]
        result = build_cached_system_param(segments)
        assert isinstance(result, str)
        assert "a" in result
        assert "b" in result

    def test_empty_segments(self):
        result = build_cached_system_param([])
        assert result == ""


class TestEstimateTokens:
    def test_english(self):
        tokens = estimate_tokens("hello world this is a test")
        assert tokens > 0
        assert tokens < 30

    def test_chinese(self):
        tokens = estimate_tokens("你好世界这是一个测试")
        assert tokens > 0
        assert tokens >= 9  # 9 Chinese chars × 1.5

    def test_mixed(self):
        tokens = estimate_tokens("hello 你好 world 世界")
        assert tokens > 0

    def test_empty(self):
        assert estimate_tokens("") == 0


class TestCacheMetrics:
    def test_defaults(self):
        m = CacheMetrics()
        assert m.cache_hit_rate == 0.0
        assert m.token_savings_pct == 0.0

    def test_hit_rate_calculation(self):
        m = CacheMetrics(
            total_calls=10,
            total_input_tokens=10000,
            cache_creation_tokens=2000,
            cache_read_tokens=8000,
        )
        assert m.cache_hit_rate == 0.8
        assert m.token_savings_pct == 80.0

    def test_to_dict(self):
        m = CacheMetrics(total_calls=5, total_input_tokens=1000)
        d = m.to_dict()
        assert d["total_calls"] == 5
        assert "cache_hit_rate" in d


class TestCacheMetricsTracker:
    @pytest.fixture
    def tracker(self, tmp_path: Path) -> CacheMetricsTracker:
        return CacheMetricsTracker(tmp_path / "test_metrics.db")

    def test_record_and_query(self, tracker: CacheMetricsTracker):
        tracker.record(
            agent="test-agent",
            model="claude-haiku",
            response_usage={
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_creation_input_tokens": 800,
                "cache_read_input_tokens": 0,
            },
        )
        tracker.record(
            agent="test-agent",
            model="claude-haiku",
            response_usage={
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 800,
            },
        )
        metrics = tracker.get_metrics()
        assert metrics.total_calls == 2
        assert metrics.total_input_tokens == 2000
        assert metrics.cache_creation_tokens == 800
        assert metrics.cache_read_tokens == 800

    def test_filter_by_agent(self, tracker: CacheMetricsTracker):
        tracker.record("agent-a", "model", {"input_tokens": 100})
        tracker.record("agent-b", "model", {"input_tokens": 200})
        m = tracker.get_metrics(agent="agent-a")
        assert m.total_calls == 1
        assert m.total_input_tokens == 100

    def test_last_n(self, tracker: CacheMetricsTracker):
        for i in range(10):
            tracker.record(
                "agent", "model",
                {"input_tokens": 100, "cache_read_input_tokens": 50},
            )
        m = tracker.get_metrics(last_n=5)
        assert m.total_calls == 5

    def test_record_with_chapter(self, tracker: CacheMetricsTracker):
        tracker.record("agent", "model", {"input_tokens": 100}, chapter=42)
        m = tracker.get_metrics()
        assert m.total_calls == 1

    def test_get_report(self, tracker: CacheMetricsTracker):
        tracker.record("a", "m", {"input_tokens": 100, "cache_read_input_tokens": 70})
        tracker.record("b", "m", {"input_tokens": 200, "cache_read_input_tokens": 150})
        report = tracker.get_report()
        assert "overall" in report
        assert "per_agent" in report
        assert "a" in report["per_agent"]
        assert "b" in report["per_agent"]

    def test_empty_metrics(self, tracker: CacheMetricsTracker):
        m = tracker.get_metrics()
        assert m.total_calls == 0
        assert m.cache_hit_rate == 0.0

    def test_cache_hit_rate_70pct(self, tracker: CacheMetricsTracker):
        """Simulate a 20-chapter run where cache hits ≥ 70%."""
        tracker.record("writer", "model", {
            "input_tokens": 5000,
            "cache_creation_input_tokens": 4000,
            "cache_read_input_tokens": 0,
        })
        for _ in range(19):
            tracker.record("writer", "model", {
                "input_tokens": 5000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 4000,
            })
        m = tracker.get_metrics()
        assert m.cache_hit_rate >= 0.70
        assert m.total_calls == 20

    def test_token_cost_down_30pct(self, tracker: CacheMetricsTracker):
        """Verify token savings math: if 40% of tokens are cache_read, savings = 40%."""
        tracker.record("writer", "model", {
            "input_tokens": 10000,
            "cache_read_input_tokens": 4000,
        })
        m = tracker.get_metrics()
        assert m.token_savings_pct >= 30.0
