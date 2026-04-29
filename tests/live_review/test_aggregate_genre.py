"""US-LR-008: 题材聚合器 aggregate_genre.py 测试。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "live-review" / "aggregate_genre.py"
_FIXTURE_CASES = _REPO_ROOT / "tests" / "live_review" / "fixtures" / "sample_30_cases"
_GENRE_SCHEMA = _REPO_ROOT / "schemas" / "live_review_genre_acceptance.schema.json"


def _run(
    cases_dir: Path,
    out_path: Path,
    *,
    min_cases: int | None = None,
    top_complaints: int | None = None,
) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(_SCRIPT),
        "--cases-dir",
        str(cases_dir),
        "--out",
        str(out_path),
    ]
    if min_cases is not None:
        args += ["--min-cases", str(min_cases)]
    if top_complaints is not None:
        args += ["--top-complaints", str(top_complaints)]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def out_path(tmp_path: Path) -> Path:
    return tmp_path / "genre_acceptance.json"


@pytest.fixture
def aggregate(out_path):
    """Run aggregator on the 30-case fixture, return parsed output dict."""
    proc = _run(_FIXTURE_CASES, out_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_output_validates_genre_acceptance_schema(aggregate):
    schema = json.loads(_GENRE_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = [e.message for e in validator.iter_errors(aggregate)]
    assert not errors, errors


def test_top_level_metadata(aggregate):
    assert aggregate["schema_version"] == "1.0"
    assert aggregate["total_novels_analyzed"] == 30
    assert aggregate["min_cases_per_genre"] == 3
    # updated_at is iso8601 (date-time format) — naive sanity check
    assert "T" in aggregate["updated_at"]


def test_excluded_genres_below_min_cases(aggregate):
    """末世 has only 2 cases (< default min_cases=3) and must be excluded."""
    genres = aggregate["genres"]
    assert "末世" not in genres, list(genres)


def test_included_genres_match_expected(aggregate):
    expected = {"都市", "重生", "玄幻", "校园", "职业流", "仙侠"}
    assert set(aggregate["genres"].keys()) == expected, set(aggregate["genres"].keys())


def test_dushi_stats_match_handcomputed(aggregate):
    """都市: 7 cases, scores=[60,65,70,75,80,55,50] → mean=65, median=65,
    p25=55, p75=75 (statistics.quantiles exclusive); pass_rate=5/7."""
    g = aggregate["genres"]["都市"]
    assert g["case_count"] == 7
    assert abs(g["score_mean"] - 65.0) < 0.01, g["score_mean"]
    assert abs(g["score_median"] - 65.0) < 0.01, g["score_median"]
    assert abs(g["score_p25"] - 55.0) < 0.01, g["score_p25"]
    assert abs(g["score_p75"] - 75.0) < 0.01, g["score_p75"]
    assert abs(g["verdict_pass_rate"] - 5 / 7) < 0.01, g["verdict_pass_rate"]


def test_chongsheng_stats_match_handcomputed(aggregate):
    """重生: 5 cases (1,2,3,4,8), scores=[60,65,70,75,62]; sorted=[60,62,65,70,75]
    mean=66.4, median=65, p25=61.0, p75=72.5; pass_rate=4/5=0.8."""
    g = aggregate["genres"]["重生"]
    assert g["case_count"] == 5
    assert abs(g["score_mean"] - 66.4) < 0.01
    assert abs(g["score_median"] - 65.0) < 0.01
    assert abs(g["score_p25"] - 61.0) < 0.01
    assert abs(g["score_p75"] - 72.5) < 0.01
    assert abs(g["verdict_pass_rate"] - 0.8) < 0.01


def test_xuanhuan_all_fail_pass_rate_zero(aggregate):
    """玄幻: 5 cases all verdict=fail → pass_rate == 0.0."""
    g = aggregate["genres"]["玄幻"]
    assert g["case_count"] == 5
    assert g["verdict_pass_rate"] == 0.0


def test_xiaoyuan_all_null_score_stats_are_null(aggregate):
    """校园: 5 cases all score=null → score_mean/median/p25/p75 all None."""
    g = aggregate["genres"]["校园"]
    assert g["case_count"] == 5
    assert g["score_mean"] is None, g["score_mean"]
    assert g["score_median"] is None, g["score_median"]
    assert g["score_p25"] is None, g["score_p25"]
    assert g["score_p75"] is None, g["score_p75"]
    # verdict all 'unknown' → no 'pass' → 0.0
    assert g["verdict_pass_rate"] == 0.0


def test_common_complaints_frequency_descending(aggregate):
    """都市 common_complaints sorted by frequency desc (non-increasing)."""
    g = aggregate["genres"]["都市"]
    cc = g["common_complaints"]
    assert len(cc) >= 5  # default top-5
    for prev, nxt in zip(cc, cc[1:], strict=False):
        assert prev["frequency"] >= nxt["frequency"], (
            f"common_complaints not descending: {prev} -> {nxt}"
        )
    # 都市 negatives by design: opening=5, pacing=4, golden_finger=3, hook=2, character=1
    # → all 5 dimensions should have strict-distinct freqs
    freqs = [c["frequency"] for c in cc[:5]]
    assert len(set(freqs)) == 5, f"top-5 freqs not unique: {freqs}"
    # opening is dominant
    assert cc[0]["dimension"] == "opening", cc[0]


def test_common_complaints_examples_present(aggregate):
    """Each complaint dict has 'examples' (≤3 raw_quote/content strings)."""
    for genre_name, g in aggregate["genres"].items():
        for c in g["common_complaints"]:
            assert "examples" in c
            assert isinstance(c["examples"], list)
            assert len(c["examples"]) <= 3, (genre_name, c)


def test_case_ids_well_formed(aggregate):
    """case_ids array per genre matches the schema pattern + non-empty."""
    import re
    pattern = re.compile(r"^CASE-LR-[0-9]{4}-[0-9]{4}$")
    for genre_name, g in aggregate["genres"].items():
        assert g["case_ids"], genre_name
        for cid in g["case_ids"]:
            assert pattern.match(cid), (genre_name, cid)


def test_top_complaints_flag_caps_list(out_path):
    proc = _run(_FIXTURE_CASES, out_path, top_complaints=2)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(out_path.read_text(encoding="utf-8"))
    for g in out["genres"].values():
        assert len(g["common_complaints"]) <= 2


def test_min_cases_threshold_changes_output(out_path):
    """Lowering min_cases to 2 should include 末世 (2 cases)."""
    proc = _run(_FIXTURE_CASES, out_path, min_cases=2)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert "末世" in out["genres"]
    assert out["min_cases_per_genre"] == 2
