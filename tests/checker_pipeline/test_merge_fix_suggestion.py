"""US-016 / F-011：merge_fix_suggestion 去重合并器单元测试。

覆盖：
- 单 checker 单 violation → 正确归入对应维度
- 多 checker 同 type → dedup + severity max + source_checkers 合并
- 主 checker 存在 → master_prompt 生效
- 主 checker 缺失 → 从 violations suggestion 合成 fix_prompt
- 从 checker 的 prompt 作为"从·<checker>"附加
- DIMENSIONS 5 个维度始终全部出现在输出里
- write_merged_fix_suggestion 写出合法 JSON
- 空输入 / 畸形输入不崩溃
- type 关键词映射：SHOT_ / SENSORY_ / SENTENCE_ / VOICE_ / DIALOGUE_
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.checker_pipeline.merge_fix_suggestion import (
    DIMENSIONS,
    MASTER_CHECKER,
    merge_fix_suggestions,
    write_merged_fix_suggestion,
)


def _report(agent: str, **kwargs) -> dict:
    base = {"agent": agent, "chapter": 1, "violations": []}
    base.update(kwargs)
    return base


class TestDimensionClassification:
    def test_shot_type_goes_to_shot(self) -> None:
        reports = [_report(
            "prose-impact-checker",
            violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "镜头单调"}],
            fix_prompt="镜头主提示",
        )]
        merged = merge_fix_suggestions(reports)
        assert len(merged["shot"]["violations"]) == 1
        assert merged["shot"]["violations"][0]["type"] == "SHOT_MONOTONY"
        assert merged["shot"]["master_checker"] == "prose-impact-checker"

    def test_sensory_type_goes_to_sensory(self) -> None:
        reports = [_report(
            "sensory-immersion-checker",
            violations=[{"type": "SENSORY_DESERT", "severity": "high", "suggestion": "补五感"}],
            fix_prompt="感官主提示",
        )]
        merged = merge_fix_suggestions(reports)
        assert len(merged["sensory"]["violations"]) == 1
        assert merged["sensory"]["master_checker"] == "sensory-immersion-checker"
        assert "感官主提示" in merged["sensory"]["fix_prompt"]

    def test_sentence_type_goes_to_rhythm(self) -> None:
        reports = [_report(
            "flow-naturalness-checker",
            violations=[{"type": "SENTENCE_RHYTHM_FLAT", "severity": "critical", "suggestion": "CV 过低"}],
            fix_prompt="句式主提示",
        )]
        merged = merge_fix_suggestions(reports)
        assert len(merged["rhythm"]["violations"]) == 1
        assert merged["rhythm"]["master_checker"] == "flow-naturalness-checker"

    def test_voice_type_goes_to_voice(self) -> None:
        reports = [_report(
            "ooc-checker",
            violations=[{"type": "VOICE_DRIFT", "severity": "high", "suggestion": "voice 漂移"}],
            fix_prompt="voice 主提示",
        )]
        merged = merge_fix_suggestions(reports)
        assert len(merged["voice"]["violations"]) == 1
        assert merged["voice"]["master_checker"] == "ooc-checker"

    def test_dialogue_type_goes_to_dialogue(self) -> None:
        reports = [_report(
            "flow-naturalness-checker",
            violations=[{"type": "DIALOGUE_NO_IDENTITY", "severity": "medium", "suggestion": "对话无辨识度"}],
            fix_prompt="对话主提示",
        )]
        merged = merge_fix_suggestions(reports)
        assert len(merged["dialogue"]["violations"]) == 1
        assert merged["dialogue"]["master_checker"] == "flow-naturalness-checker"


class TestDedup:
    def test_same_type_across_checkers_deduplicated(self) -> None:
        reports = [
            _report("prose-impact-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "medium", "suggestion": "short suggestion"}
            ]),
            _report("proofreading-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "critical", "suggestion": "much longer suggestion with more detail"}
            ]),
        ]
        merged = merge_fix_suggestions(reports)
        violations = merged["shot"]["violations"]
        assert len(violations) == 1, "same type across checkers must dedup"
        assert violations[0]["severity"] == "critical", "severity max applied"
        assert "prose-impact-checker" in violations[0]["source_checkers"]
        assert "proofreading-checker" in violations[0]["source_checkers"]
        assert "longer" in violations[0]["suggestion"], "longer suggestion wins"

    def test_different_type_not_merged(self) -> None:
        reports = [
            _report("prose-impact-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "a"},
                {"type": "SHOT_SINGLE_DOMINANCE", "severity": "critical", "suggestion": "b"},
            ]),
        ]
        merged = merge_fix_suggestions(reports)
        assert len(merged["shot"]["violations"]) == 2

    def test_severity_sort_descending(self) -> None:
        reports = [
            _report("prose-impact-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "low", "suggestion": "a"},
                {"type": "SHOT_SINGLE_DOMINANCE", "severity": "critical", "suggestion": "b"},
                {"type": "CLOSEUP_ABSENT", "severity": "high", "suggestion": "c"},
            ]),
        ]
        merged = merge_fix_suggestions(reports)
        severities = [v["severity"] for v in merged["shot"]["violations"]]
        assert severities == ["critical", "high", "low"]


class TestPromptComposition:
    def test_master_prompt_used_when_master_checker_present(self) -> None:
        reports = [_report(
            "prose-impact-checker",
            violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "s"}],
            fix_prompt="主 checker 原话",
        )]
        merged = merge_fix_suggestions(reports)
        assert "主 checker 原话" in merged["shot"]["fix_prompt"]
        assert "【镜头｜主】" in merged["shot"]["fix_prompt"]

    def test_slave_prompt_appended_as_supplement(self) -> None:
        reports = [
            _report("prose-impact-checker",
                    violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "s"}],
                    fix_prompt="主 prompt"),
            _report("proofreading-checker",
                    violations=[{"type": "SHOT_MONOTONY", "severity": "medium", "suggestion": "s2"}],
                    fix_prompt="从 prompt"),
        ]
        merged = merge_fix_suggestions(reports)
        fp = merged["shot"]["fix_prompt"]
        assert "主 prompt" in fp
        assert "从 prompt" in fp
        assert "proofreading-checker" in fp

    def test_missing_master_synthesizes_from_violations(self) -> None:
        # 没有 prose-impact-checker，但 proofreading 报了 SHOT_MONOTONY
        reports = [_report(
            "proofreading-checker",
            violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "具体修复建议"}],
        )]
        merged = merge_fix_suggestions(reports)
        fp = merged["shot"]["fix_prompt"]
        # 无主 prompt，应回落到 violations 合成
        assert "具体修复建议" in fp
        assert "SHOT_MONOTONY" in fp


class TestShape:
    def test_all_five_dimensions_always_present(self) -> None:
        merged = merge_fix_suggestions([])
        assert set(merged.keys()) == set(DIMENSIONS)
        for dim in DIMENSIONS:
            assert merged[dim]["master_checker"] == MASTER_CHECKER[dim]
            assert merged[dim]["violations"] == []
            assert merged[dim]["fix_prompt"] == ""

    def test_issues_field_also_recognized(self) -> None:
        # checker-output-schema 用 issues，不是 violations
        reports = [{
            "agent": "prose-impact-checker",
            "issues": [{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "s"}],
        }]
        merged = merge_fix_suggestions(reports)
        assert len(merged["shot"]["violations"]) == 1


class TestRobustness:
    def test_empty_input(self) -> None:
        merged = merge_fix_suggestions([])
        assert isinstance(merged, dict)
        assert set(merged.keys()) == set(DIMENSIONS)

    def test_none_input(self) -> None:
        merged = merge_fix_suggestions(None)  # type: ignore[arg-type]
        assert set(merged.keys()) == set(DIMENSIONS)

    def test_malformed_reports_skipped(self) -> None:
        reports = [
            None,  # type: ignore[list-item]
            "not a dict",  # type: ignore[list-item]
            {},  # missing agent
            {"agent": ""},  # empty agent
            _report("prose-impact-checker",
                    violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "s"}]),
        ]
        merged = merge_fix_suggestions(reports)
        assert len(merged["shot"]["violations"]) == 1

    def test_violations_without_type_use_checker_default(self) -> None:
        reports = [_report(
            "sensory-immersion-checker",
            violations=[{"severity": "high", "suggestion": "missing type"}],
        )]
        merged = merge_fix_suggestions(reports)
        # 无 type → 走 CHECKER_DEFAULT_DIMENSION (sensory)
        assert len(merged["sensory"]["violations"]) == 1
        assert merged["sensory"]["violations"][0]["type"] == "UNTYPED"


class TestWriteJson:
    def test_write_merged_fix_suggestion(self, tmp_path: Path) -> None:
        reports = [_report(
            "prose-impact-checker",
            violations=[{"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "修复镜头"}],
            fix_prompt="prompt",
        )]
        out_path = tmp_path / "merged_fix_suggestion.json"
        result = write_merged_fix_suggestion(reports, out_path)
        assert result == out_path
        assert out_path.exists()

        loaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert set(loaded.keys()) == set(DIMENSIONS)
        assert loaded["shot"]["master_checker"] == "prose-impact-checker"
        assert len(loaded["shot"]["violations"]) == 1

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        out_path = tmp_path / "nested" / "deep" / "merged.json"
        write_merged_fix_suggestion([], out_path)
        assert out_path.exists()


class TestRealisticScenario:
    def test_five_checker_overlap_dedup(self) -> None:
        """模拟真实场景：5 个 checker 同时命中 SHOT_MONOTONY/SENSORY_DESERT/SENTENCE_RHYTHM_FLAT。"""
        reports = [
            _report("prose-impact-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "high", "suggestion": "镜头 A"},
                {"type": "SENSORY_RICHNESS_LOW", "severity": "medium", "suggestion": "感官 A"},
                {"type": "SENTENCE_RHYTHM_FLAT", "severity": "critical", "suggestion": "句式 A"},
            ], fix_prompt="prose-impact 主"),
            _report("sensory-immersion-checker", violations=[
                {"type": "SENSORY_DESERT", "severity": "high", "suggestion": "感官 B"},
            ], fix_prompt="sensory 主"),
            _report("flow-naturalness-checker", violations=[
                {"type": "SENTENCE_RHYTHM_FLAT", "severity": "high", "suggestion": "句式 B"},
                {"type": "DIALOGUE_NO_IDENTITY", "severity": "medium", "suggestion": "对话 A"},
            ], fix_prompt="flow 主"),
            _report("ooc-checker", violations=[
                {"type": "VOICE_DRIFT", "severity": "medium", "suggestion": "voice A"},
            ], fix_prompt="ooc 主"),
            _report("proofreading-checker", violations=[
                {"type": "SHOT_MONOTONY", "severity": "critical", "suggestion": "镜头更详细的修复建议段落 xxxxx"},
                {"type": "SENTENCE_STRUCTURE_REPETITION", "severity": "medium", "suggestion": "句式 C"},
            ]),
        ]
        merged = merge_fix_suggestions(reports)

        # shot: 1 dedup violation，severity=critical，source_checkers 含两个
        assert len(merged["shot"]["violations"]) == 1
        v = merged["shot"]["violations"][0]
        assert v["severity"] == "critical"
        assert "prose-impact-checker" in v["source_checkers"]
        assert "proofreading-checker" in v["source_checkers"]

        # sensory: 2 violations（SENSORY_RICHNESS_LOW + SENSORY_DESERT）
        assert len(merged["sensory"]["violations"]) == 2

        # rhythm: SENTENCE_RHYTHM_FLAT dedup；SENTENCE_STRUCTURE_REPETITION 独立
        rhythm_types = {v["type"] for v in merged["rhythm"]["violations"]}
        assert "SENTENCE_RHYTHM_FLAT" in rhythm_types
        assert "SENTENCE_STRUCTURE_REPETITION" in rhythm_types

        # voice: 1 violation
        assert len(merged["voice"]["violations"]) == 1

        # dialogue: 1 violation
        assert len(merged["dialogue"]["violations"]) == 1

        # 确认主 prompt 都进入了相应维度
        assert "prose-impact 主" in merged["shot"]["fix_prompt"]
        assert "sensory 主" in merged["sensory"]["fix_prompt"]
        assert "flow 主" in merged["rhythm"]["fix_prompt"] or "flow 主" in merged["dialogue"]["fix_prompt"]
        assert "ooc 主" in merged["voice"]["fix_prompt"]
