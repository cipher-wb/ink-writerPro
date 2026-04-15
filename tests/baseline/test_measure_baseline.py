#!/usr/bin/env python3
"""Tests for scripts/measure_baseline.py — validates JSON schema and idempotency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "ink-writer" / "scripts"))

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager

REQUIRED_TOP_KEYS = {"version", "timestamp", "git_sha", "project_root",
                     "chapter_count", "entity_count", "metrics", "detail",
                     "sample_counts"}

REQUIRED_METRIC_KEYS = {"hook_density", "strong_hook_ratio", "avg_micropayoffs",
                        "avg_debt_balance", "high_point_density", "high_point_stdev",
                        "emotion_variance", "avg_immersion", "ai_taste_score",
                        "ai_taste_stdev", "ooc_score", "ooc_stdev",
                        "consistency_score", "consistency_stdev",
                        "avg_chapter_seconds", "avg_chapter_tokens"}

REQUIRED_DETAIL_KEYS = {"hook", "high_point", "emotion", "ai_taste", "ooc",
                        "consistency", "performance", "tokens", "review_aggregate"}

REQUIRED_SAMPLE_KEYS = {"hook", "high_point", "emotion", "ai_taste", "ooc",
                        "consistency", "performance", "tokens"}


def _seed_test_data(manager: IndexManager) -> None:
    """Insert test data into an already-initialized IndexManager DB."""
    with manager._get_conn() as conn:
        c = conn.cursor()

        for i in range(1, 6):
            c.execute(
                "INSERT OR REPLACE INTO chapters (chapter, title, word_count) VALUES (?, ?, ?)",
                (i, f"Chapter {i}", 2500),
            )
            c.execute(
                "INSERT OR REPLACE INTO chapter_reading_power "
                "(chapter, hook_type, hook_strength, micropayoffs, debt_balance) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    i,
                    "危机钩" if i % 2 else "悬念钩",
                    "strong" if i <= 3 else "medium",
                    json.dumps(["能力兑现", "认可兑现"] if i % 2 else ["能力兑现"]),
                    0.0 if i <= 3 else 0.5,
                ),
            )

        dims = {
            "reader-pull-checker": 85,
            "high-point-checker": 78,
            "anti-detection-checker": 72,
            "ooc-checker": 90,
            "consistency-checker": 88,
            "pacing-checker": 80,
        }
        sevs = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        payload = {"reader-simulator": {"metrics": {"immersion_score": 75}}}

        for i in range(1, 6):
            c.execute(
                "INSERT OR REPLACE INTO review_metrics "
                "(start_chapter, end_chapter, overall_score, "
                "dimension_scores, severity_counts, review_payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (i, i, 82.0 + i, json.dumps(dims), json.dumps(sevs), json.dumps(payload)),
            )

        for i in range(1, 4):
            c.execute(
                "INSERT INTO tool_call_stats (tool_name, success, chapter) "
                "VALUES (?, ?, ?)",
                ("write_chapter", 1, i),
            )

        conn.commit()


def _create_fixture_project(tmp_path: Path) -> Path:
    """Create a minimal project structure with seeded data."""
    project_root = tmp_path / "test-project"
    project_root.mkdir()
    ink_dir = project_root / ".ink"
    ink_dir.mkdir()
    (ink_dir / "reports").mkdir()

    state = {"progress": {"current_chapter": 5}}
    (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

    cfg = DataModulesConfig.from_project_root(project_root)
    manager = IndexManager(cfg)
    _seed_test_data(manager)
    return project_root


def _create_empty_project(tmp_path: Path) -> Path:
    """Create a project with empty tables (no data)."""
    project_root = tmp_path / "empty-project"
    project_root.mkdir()
    ink_dir = project_root / ".ink"
    ink_dir.mkdir()
    (ink_dir / "state.json").write_text("{}", encoding="utf-8")

    cfg = DataModulesConfig.from_project_root(project_root)
    IndexManager(cfg)
    return project_root


@pytest.fixture
def fixture_project(tmp_path):
    return _create_fixture_project(tmp_path)


@pytest.fixture
def empty_project(tmp_path):
    return _create_empty_project(tmp_path)


def test_measure_baseline_json_schema(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert REQUIRED_TOP_KEYS.issubset(baseline.keys()), \
        f"Missing top keys: {REQUIRED_TOP_KEYS - baseline.keys()}"
    assert REQUIRED_METRIC_KEYS.issubset(baseline["metrics"].keys()), \
        f"Missing metric keys: {REQUIRED_METRIC_KEYS - baseline['metrics'].keys()}"
    assert REQUIRED_DETAIL_KEYS.issubset(baseline["detail"].keys()), \
        f"Missing detail keys: {REQUIRED_DETAIL_KEYS - baseline['detail'].keys()}"
    assert REQUIRED_SAMPLE_KEYS.issubset(baseline["sample_counts"].keys()), \
        f"Missing sample keys: {REQUIRED_SAMPLE_KEYS - baseline['sample_counts'].keys()}"


def test_metrics_are_numeric(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    for key, val in baseline["metrics"].items():
        assert isinstance(val, (int, float)), f"metrics.{key} should be numeric, got {type(val)}"


def test_hook_density_correct(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["metrics"]["hook_density"] == 1.0
    assert baseline["metrics"]["strong_hook_ratio"] == 0.6
    assert baseline["sample_counts"]["hook"] == 5


def test_high_point_density_correct(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["metrics"]["high_point_density"] == 78.0
    assert baseline["sample_counts"]["high_point"] == 5


def test_ai_taste_score_correct(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["metrics"]["ai_taste_score"] == 72.0
    assert baseline["sample_counts"]["ai_taste"] == 5


def test_ooc_score_correct(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["metrics"]["ooc_score"] == 90.0


def test_consistency_score_correct(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["metrics"]["consistency_score"] == 88.0


def test_timestamp_and_version(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)

    assert baseline["version"] == "v12"
    assert "T" in baseline["timestamp"]
    assert isinstance(baseline["git_sha"], str)
    assert len(baseline["git_sha"]) > 0


def test_idempotency(fixture_project):
    from measure_baseline import measure_baseline

    b1 = measure_baseline(fixture_project)
    b2 = measure_baseline(fixture_project)

    assert b1["metrics"] == b2["metrics"]
    assert b1["sample_counts"] == b2["sample_counts"]
    assert b1["detail"]["hook"] == b2["detail"]["hook"]


def test_json_serializable(fixture_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(fixture_project)
    serialized = json.dumps(baseline, ensure_ascii=False)
    deserialized = json.loads(serialized)

    assert deserialized["metrics"] == baseline["metrics"]


def test_empty_project(empty_project):
    from measure_baseline import measure_baseline

    baseline = measure_baseline(empty_project)

    assert baseline["metrics"]["hook_density"] == 0.0
    assert baseline["metrics"]["high_point_density"] == 0.0
    assert baseline["chapter_count"] == 0
    assert all(v == 0 for v in baseline["sample_counts"].values())
