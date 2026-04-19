"""US-012 (v18): arbitration matrix — config/arbitration.yaml drives the
overlap-checker list so adding a new entry requires *zero* Python changes.

Covers:
- default matrix load: production yaml parses and exposes the v18 US-011 trio
- severity_priority map loads from yaml (not hardcoded constants)
- extending the matrix: a new symptom_key_group entry makes
  ``collect_issues_from_review_metrics`` pick up the new checker without any
  Python edit to arbitration.py
- missing yaml falls back to hardcoded defaults (best-effort pipeline)
- malformed yaml falls back to defaults (does not raise)
- NG-3 / G003 guard: the production yaml's top-of-file comment names the
  16-checker constraint so future edits stay honest
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.editor_wisdom import arbitration as arb_mod
from ink_writer.editor_wisdom.arbitration import (
    _FALLBACK_CHECKERS,
    _FALLBACK_SEVERITY_PRIORITY,
    arbitrate_generic,
    collect_issues_from_review_metrics,
    load_arbitration_matrix,
)

_PROD_YAML = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "arbitration.yaml"
)


# ---------------------------------------------------------------------------
# production yaml sanity
# ---------------------------------------------------------------------------


def test_production_yaml_exists_and_parses() -> None:
    """The shipped yaml must exist and load without error."""
    assert _PROD_YAML.exists(), f"missing {_PROD_YAML}"
    checkers, severity = load_arbitration_matrix(_PROD_YAML)
    # production trio (v18 US-011 defaults)
    assert "prose-impact-checker" in checkers
    assert "sensory-immersion-checker" in checkers
    assert "flow-naturalness-checker" in checkers
    # severity→priority matches the v18 contract
    assert severity["critical"] == "P2"
    assert severity["info"] == "P4"


def test_production_yaml_header_documents_ng3_constraint() -> None:
    """NG-3 / G003 constraint (do not collapse the 16 checker specs) must be
    called out at the top of the yaml so edits stay honest."""
    text = _PROD_YAML.read_text(encoding="utf-8")
    head = text[: 2000].lower()
    assert "ng-3" in head or "ng3" in head or "g003" in head, (
        "yaml must reference the NG-3 / G003 constraint in its header"
    )
    assert "16" in head, "yaml header must reference the 16-checker count"


def test_module_defaults_match_loaded_matrix() -> None:
    """Module-level ``_GENERIC_CHECKERS`` is the cached load of the yaml."""
    checkers, severity = load_arbitration_matrix()
    assert checkers == arb_mod._GENERIC_CHECKERS
    assert severity == arb_mod._GENERIC_SEVERITY_PRIORITY


# ---------------------------------------------------------------------------
# extensibility: a new entry → no Python change required
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_new_matrix_entry_picked_up_without_code_change(tmp_path: Path) -> None:
    """Core US-012 AC: appending a new ``symptom_key_groups`` entry in the
    yaml alone is enough for ``collect_issues_from_review_metrics`` to accept
    the new checker's output and ``arbitrate_generic`` to merge it.

    No change to ``ink_writer/editor_wisdom/arbitration.py`` is required —
    the test uses the *production* arbitrate_generic path with a matrix
    loaded from a tmp yaml.
    """
    yaml_path = tmp_path / "arbitration.yaml"
    _write_yaml(
        yaml_path,
        """
# Test-only matrix: adds a new overlap group "emotion_issue" with a brand
# new checker "emotion-curve-checker" alongside the existing flow_issue.
symptom_key_groups:
  flow_issue:
    checkers:
      - prose-impact-checker
      - sensory-immersion-checker
      - flow-naturalness-checker
  emotion_issue:
    description: "emotion curve overlap with prose-impact"
    checkers:
      - emotion-curve-checker
      - prose-impact-checker
severity_priority:
  critical: P2
  high: P2
  medium: P3
  low: P3
  info: P4
""".strip(),
    )
    checkers, severity = load_arbitration_matrix(yaml_path)
    assert "emotion-curve-checker" in checkers, (
        "new matrix entry must be exposed without Python changes"
    )
    assert len(checkers) == 4  # 3 existing + 1 new, deduped

    # End-to-end: using the new checker list, a violation from the new
    # checker and an existing one should fold via arbitrate_generic.
    metrics = {
        "critical_issues": [],
        "review_payload_json": {
            "checker_results": {
                "emotion-curve-checker": {
                    "violations": [
                        {
                            "type": "EMOTION_FLAT",
                            "severity": "high",
                            "suggestion": "情绪曲线过平",
                        }
                    ]
                },
                "prose-impact-checker": {
                    "violations": [
                        {
                            "type": "EMOTION_FLAT",
                            "severity": "medium",
                            "suggestion": "叙事张力不足",
                        }
                    ]
                },
            }
        },
    }
    issues = collect_issues_from_review_metrics(metrics, checkers=checkers)
    assert len(issues) == 2

    result = arbitrate_generic(chapter_id=50, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 1, (
        "same symptom_key across two matrix checkers must fold to 1 fix"
    )
    merged = result["merged_fixes"][0]
    assert set(merged["sources"]) == {
        "emotion-curve-checker#EMOTION_FLAT",
        "prose-impact-checker#EMOTION_FLAT",
    }


def test_severity_priority_from_yaml_overrides_defaults(tmp_path: Path) -> None:
    """Severity → priority map is yaml-driven, not hardcoded in Python."""
    yaml_path = tmp_path / "arbitration.yaml"
    _write_yaml(
        yaml_path,
        """
symptom_key_groups:
  flow_issue:
    checkers:
      - prose-impact-checker
severity_priority:
  critical: P3   # downgraded (non-default)
  medium: P2    # upgraded (non-default)
  info: P4
""".strip(),
    )
    _, severity = load_arbitration_matrix(yaml_path)
    assert severity["critical"] == "P3"
    assert severity["medium"] == "P2"
    # unspecified keys are simply absent — caller fallback path elsewhere
    assert "high" not in severity


# ---------------------------------------------------------------------------
# best-effort fallback paths
# ---------------------------------------------------------------------------


def test_missing_yaml_falls_back_to_hardcoded_defaults(tmp_path: Path) -> None:
    """Pipeline must stay up even if config/arbitration.yaml is absent."""
    missing = tmp_path / "does-not-exist.yaml"
    checkers, severity = load_arbitration_matrix(missing)
    assert checkers == _FALLBACK_CHECKERS
    assert severity == _FALLBACK_SEVERITY_PRIORITY


def test_malformed_yaml_falls_back_without_raising(tmp_path: Path) -> None:
    """A syntactically broken yaml must not crash the pipeline."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("not: [valid yaml: here", encoding="utf-8")
    checkers, severity = load_arbitration_matrix(broken)
    assert checkers == _FALLBACK_CHECKERS
    assert severity == _FALLBACK_SEVERITY_PRIORITY


def test_empty_yaml_falls_back(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    checkers, severity = load_arbitration_matrix(empty)
    assert checkers == _FALLBACK_CHECKERS
    assert severity == _FALLBACK_SEVERITY_PRIORITY


def test_yaml_without_groups_key_falls_back(tmp_path: Path) -> None:
    """A yaml missing ``symptom_key_groups`` keeps fallback checkers intact
    so we don't silently run with an empty overlap list."""
    y = tmp_path / "no-groups.yaml"
    y.write_text(
        "severity_priority:\n  critical: P2\n", encoding="utf-8"
    )
    checkers, severity = load_arbitration_matrix(y)
    assert checkers == _FALLBACK_CHECKERS
    assert severity["critical"] == "P2"  # severity still picked up


# ---------------------------------------------------------------------------
# NG-3 / G003 regression guard
# ---------------------------------------------------------------------------


def test_ng3_guard_ch3_unchanged(tmp_path: Path) -> None:
    """NG-3: chapter 1-3 ignore the generic matrix path entirely."""
    yaml_path = tmp_path / "arbitration.yaml"
    _write_yaml(
        yaml_path,
        """
symptom_key_groups:
  anything:
    checkers:
      - whatever-checker
""".strip(),
    )
    checkers, _ = load_arbitration_matrix(yaml_path)
    assert "whatever-checker" in checkers
    # even with a broadened matrix, ch ≤ 3 never invokes generic arbitration
    result = arbitrate_generic(
        chapter_id=3,
        issues=[
            arb_mod.Issue(
                source="whatever-checker#X",
                priority="P2",
                fix_prompt="x",
                symptom_key="x",
            )
        ],
    )
    assert result is None


@pytest.mark.parametrize(
    "duplicate_yaml",
    [
        """
symptom_key_groups:
  a:
    checkers: [prose-impact-checker, sensory-immersion-checker]
  b:
    checkers: [prose-impact-checker, flow-naturalness-checker]
""".strip(),
    ],
)
def test_duplicate_checker_across_groups_dedupes(
    tmp_path: Path, duplicate_yaml: str
) -> None:
    """A checker listed in two groups must appear once in the flat list."""
    y = tmp_path / "dup.yaml"
    y.write_text(duplicate_yaml, encoding="utf-8")
    checkers, _ = load_arbitration_matrix(y)
    assert sorted(checkers) == sorted(
        {
            "prose-impact-checker",
            "sensory-immersion-checker",
            "flow-naturalness-checker",
        }
    )
    assert len(checkers) == 3
