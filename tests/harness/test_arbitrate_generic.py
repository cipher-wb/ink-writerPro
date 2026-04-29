"""US-011 (v18 AUDIT-V17-R008): arbitrate_generic folds overlapping
prose-craft checker output for chapter >= 4.

Covers:
- ch 50 with prose-impact + sensory-immersion + flow-naturalness firing on
  the same symptom_key → single merged fix_prompt
- ch < 4 returns None (golden-three path owns its own arbitrate)
- ch 1-3 arbitrate still works unchanged (NG-3 guard)
- collect_issues_from_review_metrics normalizes type → symptom_key so
  cross-checker duplicates collide into one bucket
- pipeline_manager._arbitrate_chapter_issues end-to-end (sqlite fixture)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ink_writer.editor_wisdom.arbitration import (
    Issue,
    arbitrate,
    arbitrate_generic,
    collect_issues_from_review_metrics,
)


def _issue(source: str, priority: str, fix: str, symptom: str, direction: str = "forward") -> Issue:
    return Issue(
        source=source,
        priority=priority,
        fix_prompt=fix,
        symptom_key=symptom,
        direction=direction,
    )


def test_ch50_triple_overlap_merges_to_single_fix_prompt() -> None:
    """AUDIT-V17-R008 golden path: 3 overlap checkers → 1 merged fix_prompt."""
    issues = [
        _issue(
            "prose-impact-checker#SHOT_MONOTONY",
            "P2",
            "镜头切换过于单调，建议穿插远景/特写",
            "shot_monotony",
        ),
        _issue(
            "sensory-immersion-checker#SHOT_MONOTONY",
            "P3",
            "感官层面镜头节奏缺乏层次",
            "shot_monotony",
        ),
        _issue(
            "flow-naturalness-checker#SHOT_MONOTONY",
            "P3",
            "叙事流畅度受镜头单调拖累",
            "shot_monotony",
        ),
    ]
    result = arbitrate_generic(chapter_id=50, issues=issues)
    assert result is not None
    assert result["mode"] == "generic"
    assert result["chapter_id"] == 50
    assert len(result["merged_fixes"]) == 1, (
        f"3 overlap checkers must fold into 1 fix, got {result['merged_fixes']}"
    )

    merged = result["merged_fixes"][0]
    assert merged["priority"] == "P2"  # highest of the three
    assert merged["fix_prompt"] == "镜头切换过于单调，建议穿插远景/特写"
    assert set(merged["sources"]) == {
        "prose-impact-checker#SHOT_MONOTONY",
        "sensory-immersion-checker#SHOT_MONOTONY",
        "flow-naturalness-checker#SHOT_MONOTONY",
    }
    assert merged["context_addendum"] is not None
    assert "sensory-immersion-checker" in merged["context_addendum"]
    assert "flow-naturalness-checker" in merged["context_addendum"]
    assert merged["issue_id"].startswith("ARBG-")
    assert result["dropped"] == []


def test_arbitrate_generic_returns_none_for_ch_below_4() -> None:
    """ch 1-3 must not hit the generic path; caller dispatches to ``arbitrate``."""
    issues = [_issue("prose-impact-checker#X", "P2", "x", "s")]
    assert arbitrate_generic(chapter_id=1, issues=issues) is None
    assert arbitrate_generic(chapter_id=2, issues=issues) is None
    assert arbitrate_generic(chapter_id=3, issues=issues) is None


def test_arbitrate_generic_parallel_fixes_when_no_overlap() -> None:
    """Independent symptom_keys emit independent merged fixes."""
    issues = [
        _issue("prose-impact-checker#A", "P2", "fix A", "shot_monotony"),
        _issue("sensory-immersion-checker#B", "P3", "fix B", "visual_overload"),
        _issue("flow-naturalness-checker#C", "P3", "fix C", "sentence_rhythm_flat"),
    ]
    result = arbitrate_generic(chapter_id=50, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 3
    priorities = [m["priority"] for m in result["merged_fixes"]]
    assert priorities == sorted(priorities)  # ascending P0 first
    assert result["dropped"] == []


def test_arbitrate_generic_reverse_conflict_drops_lower() -> None:
    """Same symptom, opposite directions → lower-priority side enters ``dropped``."""
    issues = [
        _issue(
            "prose-impact-checker#X",
            "P2",
            "加长战斗镜头描写",
            "combat_length",
            direction="expand",
        ),
        _issue(
            "flow-naturalness-checker#X",
            "P3",
            "战斗描写过长，压缩节奏",
            "combat_length",
            direction="shrink",
        ),
    ]
    result = arbitrate_generic(chapter_id=50, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 1
    assert result["merged_fixes"][0]["priority"] == "P2"
    assert len(result["dropped"]) == 1
    assert result["dropped"][0]["source"] == "flow-naturalness-checker#X"
    assert "P2" in result["dropped"][0]["reason"]


def test_golden_three_arbitrate_unchanged_by_us011() -> None:
    """NG-3 guard: existing ch 1-3 path behavior must not regress."""
    issues = [
        _issue("golden-three-checker#H-01", "P0", "开篇钩子不足", "ch1_hook"),
        _issue("editor_wisdom#EW-0120", "P3", "加对话钩", "ch1_hook"),
    ]
    result = arbitrate(chapter_id=1, issues=issues)
    assert result is not None
    assert len(result["merged_fixes"]) == 1
    fix = result["merged_fixes"][0]
    assert fix["priority"] == "P0"
    assert fix["fix_prompt"] == "开篇钩子不足"
    assert fix["issue_id"].startswith("ARB-")  # not ARBG-
    assert result["mode"] == "golden"


def test_arbitrate_p4_info_still_filtered_in_generic() -> None:
    """P4 info never produces a merged fix (consistent with ``arbitrate``)."""
    issues = [
        _issue("prose-impact-checker#INFO", "P4", "仅供参考", "tone_note"),
    ]
    result = arbitrate_generic(chapter_id=10, issues=issues)
    assert result is not None
    assert result["merged_fixes"] == []
    assert result["dropped"] == []


# ---------------------------------------------------------------------------
# collect_issues_from_review_metrics
# ---------------------------------------------------------------------------


def test_collect_issues_normalizes_type_to_symptom_key() -> None:
    """Different surviving ``type`` spellings collide after normalization.

    US-006 后默认全场景直白模式会过滤 sensory-immersion，并豁免
    prose-impact / flow-naturalness 的镜头/感官软规则；这里使用非豁免的
    sentence rhythm 类型来锁定 collector 的归一化行为。
    """
    metrics = {
        "critical_issues": [],
        "review_payload_json": {
            "checker_results": {
                "prose-impact-checker": {
                    "violations": [
                        {
                            "type": "SENTENCE_RHYTHM_FLAT",
                            "severity": "high",
                            "suggestion": "A",
                        }
                    ]
                },
                "flow-naturalness-checker": {
                    "issues": [
                        {
                            "type": "sentence.rhythm-flat",
                            "severity": "low",
                            "suggestion": "C",
                        }
                    ]
                },
            }
        },
    }
    issues = collect_issues_from_review_metrics(metrics)
    assert len(issues) == 2
    # both surviving issues should share a single normalized symptom_key
    keys = {it.symptom_key for it in issues}
    assert len(keys) == 1, f"expected 1 normalized key, got {keys}"


def test_collect_issues_parses_json_strings() -> None:
    """Raw DB row stores ``review_payload_json`` as TEXT; helper must deserialize."""
    payload = {
        "checker_results": {
            "prose-impact-checker": {
                "violations": [
                    {"type": "X", "severity": "critical", "suggestion": "fix x"}
                ]
            }
        }
    }
    metrics = {
        "critical_issues": "[]",
        "review_payload_json": json.dumps(payload),
    }
    issues = collect_issues_from_review_metrics(metrics)
    assert len(issues) == 1
    assert issues[0].priority == "P2"
    assert issues[0].fix_prompt == "fix x"


def test_collect_issues_ignores_non_overlap_checkers() -> None:
    """NG-3: only the 3 prose-craft checkers feed generic arbitration."""
    metrics = {
        "review_payload_json": {
            "checker_results": {
                "logic-checker": {
                    "violations": [
                        {"type": "X", "severity": "critical", "suggestion": "ignore"}
                    ]
                },
                "ooc-checker": {
                    "violations": [
                        {"type": "Y", "severity": "high", "suggestion": "ignore"}
                    ]
                },
            }
        }
    }
    assert collect_issues_from_review_metrics(metrics) == []


def test_collect_issues_handles_none_and_empty() -> None:
    assert collect_issues_from_review_metrics(None) == []
    assert collect_issues_from_review_metrics({}) == []
    assert collect_issues_from_review_metrics({"review_payload_json": None}) == []


# ---------------------------------------------------------------------------
# pipeline_manager integration
# ---------------------------------------------------------------------------


def _seed_review_metrics(db_path: Path, chapter: int) -> None:
    """Create a minimal index.db with a single review_metrics row for ``chapter``."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE review_metrics (
                start_chapter INTEGER,
                end_chapter INTEGER,
                overall_score REAL,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                report_file TEXT,
                notes TEXT,
                review_payload_json TEXT,
                updated_at TEXT,
                PRIMARY KEY (start_chapter, end_chapter)
            )
            """
        )
        payload = {
            "checker_results": {
                "prose-impact-checker": {
                    "violations": [
                        {
                            "type": "SENTENCE_RHYTHM_FLAT",
                            "severity": "high",
                            "suggestion": "句式节奏增加顿挫",
                        }
                    ]
                },
                "flow-naturalness-checker": {
                    "violations": [
                        {
                            "type": "sentence.rhythm-flat",
                            "severity": "low",
                            "suggestion": "节奏更自然",
                        }
                    ]
                },
            }
        }
        conn.execute(
            """
            INSERT INTO review_metrics
              (start_chapter, end_chapter, overall_score, dimension_scores,
               severity_counts, critical_issues, report_file, notes,
               review_payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                chapter,
                chapter,
                80.0,
                "{}",
                "{}",
                "[]",
                "",
                "",
                json.dumps(payload),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_pipeline_manager_arbitrate_chapter_issues_ch50(tmp_path: Path) -> None:
    """End-to-end: pipeline_manager reads review_metrics → writes arbitration.json."""
    from ink_writer.parallel.pipeline_manager import PipelineConfig, PipelineManager

    project_root = tmp_path
    ink_dir = project_root / ".ink"
    ink_dir.mkdir()
    db_path = ink_dir / "index.db"
    _seed_review_metrics(db_path, chapter=50)

    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    config = PipelineConfig(
        project_root=project_root,
        plugin_root=plugin_root,
        parallel=1,
    )
    mgr = PipelineManager(config)
    result = mgr._arbitrate_chapter_issues(50)

    assert result is not None
    assert result["mode"] == "generic"
    assert result["chapter_id"] == 50
    assert len(result["merged_fixes"]) == 1
    merged = result["merged_fixes"][0]
    assert len(merged["sources"]) == 2

    out_path = project_root / ".ink" / "arbitration" / "ch0050.json"
    assert out_path.exists(), "arbitration payload must be persisted for polish-agent"
    persisted = json.loads(out_path.read_text(encoding="utf-8"))
    assert persisted == result


def test_pipeline_manager_arbitrate_chapter_ch3_is_noop(tmp_path: Path) -> None:
    """ch < 4 must not produce a generic arbitration file (NG-3 guard)."""
    from ink_writer.parallel.pipeline_manager import PipelineConfig, PipelineManager

    project_root = tmp_path
    ink_dir = project_root / ".ink"
    ink_dir.mkdir()
    db_path = ink_dir / "index.db"
    _seed_review_metrics(db_path, chapter=3)

    config = PipelineConfig(
        project_root=project_root,
        plugin_root=tmp_path / "plugin",
        parallel=1,
    )
    (tmp_path / "plugin").mkdir()
    mgr = PipelineManager(config)
    assert mgr._arbitrate_chapter_issues(3) is None
    assert not (project_root / ".ink" / "arbitration").exists()


def test_pipeline_manager_arbitrate_missing_db_returns_none(tmp_path: Path) -> None:
    """Best-effort path: no index.db → None, no crash."""
    from ink_writer.parallel.pipeline_manager import PipelineConfig, PipelineManager

    (tmp_path / "plugin").mkdir()
    config = PipelineConfig(
        project_root=tmp_path,
        plugin_root=tmp_path / "plugin",
        parallel=1,
    )
    mgr = PipelineManager(config)
    assert mgr._arbitrate_chapter_issues(50) is None
