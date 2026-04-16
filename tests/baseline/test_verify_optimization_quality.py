"""Tests for scripts/verify_optimization_quality.py"""

import json
import os

from verify_optimization_quality import (
    compare_metrics,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_review(
    overall: float = 85.0,
    checkers: dict | None = None,
    entity_count: int = 0,
) -> dict:
    """Build a minimal review report dict."""
    cr = {}
    for name, (score, issues_count) in (checkers or {}).items():
        cr[name] = {
            "agent": name,
            "overall_score": score,
            "pass": True,
            "issues": [{"id": f"I{i}", "severity": "low"} for i in range(issues_count)],
            "metrics": {},
            "summary": "ok",
        }
    return {
        "overall_score": overall,
        "checker_results": cr,
        "review_payload_json": {"entity_count": entity_count},
    }


def _write_reports(tmpdir: str, reports: list[dict], prefix: str = "review_ch") -> None:
    for i, r in enumerate(reports, start=1):
        path = os.path.join(tmpdir, f"{prefix}{i:03d}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(r, fh)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestAllPass:
    """Scenario: all metrics within threshold → PASS."""

    def test_all_pass(self, tmp_path):
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        before_report = _make_review(
            overall=85.0,
            checkers={"logic": (80, 2), "consistency": (90, 1)},
            entity_count=50,
        )
        after_report = _make_review(
            overall=84.0,
            checkers={"logic": (79, 2), "consistency": (88, 1)},
            entity_count=49,
        )

        _write_reports(str(before_dir), [before_report])
        _write_reports(str(after_dir), [after_report])

        rc = main(["--before", str(before_dir), "--after", str(after_dir)])
        assert rc == 0


class TestScoreFail:
    """Scenario: overall_score drop exceeds threshold → FAIL."""

    def test_overall_score_fail(self, tmp_path):
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        before_report = _make_review(overall=85.0, checkers={"logic": (80, 1)}, entity_count=50)
        # Drop of 5 points → exceeds threshold of 2
        after_report = _make_review(overall=80.0, checkers={"logic": (80, 1)}, entity_count=50)

        _write_reports(str(before_dir), [before_report])
        _write_reports(str(after_dir), [after_report])

        rc = main(["--before", str(before_dir), "--after", str(after_dir)])
        assert rc == 1

    def test_checker_score_fail(self, tmp_path):
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        before_report = _make_review(overall=85.0, checkers={"logic": (85, 1)}, entity_count=50)
        # logic drops by 5 → exceeds checker threshold of 3
        after_report = _make_review(overall=84.0, checkers={"logic": (80, 1)}, entity_count=50)

        _write_reports(str(before_dir), [before_report])
        _write_reports(str(after_dir), [after_report])

        rc = main(["--before", str(before_dir), "--after", str(after_dir)])
        assert rc == 1


class TestIssuesFail:
    """Scenario: after has too many more issues than before → FAIL."""

    def test_issues_count_fail(self, tmp_path):
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        before_report = _make_review(overall=85.0, checkers={"logic": (80, 1)}, entity_count=50)
        # After has 4 issues vs before's 1 → extra = 3 > allowed 1
        after_report = _make_review(overall=85.0, checkers={"logic": (80, 4)}, entity_count=50)

        _write_reports(str(before_dir), [before_report])
        _write_reports(str(after_dir), [after_report])

        rc = main(["--before", str(before_dir), "--after", str(after_dir)])
        assert rc == 1


class TestEntityFail:
    """Scenario: entity extraction count diverges > 5% → FAIL."""

    def test_entity_count_fail(self, tmp_path):
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        before_report = _make_review(overall=85.0, checkers={"logic": (80, 1)}, entity_count=100)
        # Entity count drops by 10% → exceeds 5% threshold
        after_report = _make_review(overall=85.0, checkers={"logic": (80, 1)}, entity_count=90)

        _write_reports(str(before_dir), [before_report])
        _write_reports(str(after_dir), [after_report])

        rc = main(["--before", str(before_dir), "--after", str(after_dir)])
        assert rc == 1


class TestCompareMetrics:
    """Direct unit tests for compare_metrics."""

    def test_boundary_pass(self):
        """Exactly at threshold → still PASS."""
        before = {"avg_overall": 85.0, "avg_checker": {"logic": 80.0}, "total_issues": 2, "entity_count": 100}
        after = {"avg_overall": 83.0, "avg_checker": {"logic": 77.0}, "total_issues": 3, "entity_count": 95}
        passed, _ = compare_metrics(before, after)
        assert passed is True

    def test_zero_entities(self):
        """Both zero entities → PASS (no division by zero)."""
        before = {"avg_overall": 85.0, "avg_checker": {}, "total_issues": 0, "entity_count": 0}
        after = {"avg_overall": 85.0, "avg_checker": {}, "total_issues": 0, "entity_count": 0}
        passed, _ = compare_metrics(before, after)
        assert passed is True
