#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for computational_checks.py — Step 2C gate."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from computational_checks import (
    CheckResult,
    check_character_conflicts,
    check_contract_completeness,
    check_dialogue_ratio,
    check_file_naming,
    check_foreshadowing_consistency,
    check_metadata_leakage,
    check_opening_pattern,
    check_power_level,
    check_word_count,
    main,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

class TestCheckResult:
    def test_to_dict_without_detail(self):
        r = CheckResult("test", True, "soft", "ok")
        d = r.to_dict()
        assert d == {"name": "test", "passed": True, "severity": "soft", "message": "ok"}
        assert "detail" not in d

    def test_to_dict_with_detail(self):
        r = CheckResult("test", False, "hard", "fail", detail="some detail")
        d = r.to_dict()
        assert d["detail"] == "some detail"
        assert d["passed"] is False


# ---------------------------------------------------------------------------
# check_word_count
# ---------------------------------------------------------------------------

class TestCheckWordCount:
    def test_pass_normal(self):
        text = "字" * 3000
        r = check_word_count(text)
        assert r.passed is True
        assert r.severity == "soft"

    def test_fail_too_short(self):
        text = "字" * 100
        r = check_word_count(text)
        assert r.passed is False
        assert r.severity == "hard"
        assert "100" in r.message

    def test_soft_warning_too_long(self):
        text = "字" * 6000
        r = check_word_count(text)
        assert r.passed is False
        assert r.severity == "soft"
        assert "6000" in r.message

    def test_markdown_headings_stripped(self):
        # Markdown headings should not count toward word count
        heading = "# 第一章 标题\n## 小节\n"
        body = "字" * 2500
        r = check_word_count(heading + body)
        assert r.passed is True

    def test_whitespace_stripped(self):
        text = " 字 " * 2500  # whitespace should be removed
        r = check_word_count(text)
        assert r.passed is True

    def test_exact_min_boundary(self):
        r = check_word_count("字" * 2200)
        assert r.passed is True

    def test_exact_max_boundary(self):
        r = check_word_count("字" * 5000)
        assert r.passed is True


# ---------------------------------------------------------------------------
# check_file_naming
# ---------------------------------------------------------------------------

class TestCheckFileNaming:
    def test_pass_standard_format(self):
        r = check_file_naming(Path("第0005章-冲突.md"), 5)
        assert r.passed is True

    def test_pass_no_title(self):
        r = check_file_naming(Path("第0005章.md"), 5)
        assert r.passed is True

    def test_pass_no_leading_zeros(self):
        r = check_file_naming(Path("第5章.md"), 5)
        assert r.passed is True

    def test_fail_wrong_chapter_num(self):
        r = check_file_naming(Path("第0003章.md"), 5)
        assert r.passed is False
        assert r.severity == "hard"

    def test_fail_wrong_extension(self):
        # Name matches pattern but extension is not .md
        r = check_file_naming(Path("第0005章.txt"), 5)
        assert r.passed is False
        assert r.severity == "hard"

    def test_fail_completely_wrong(self):
        r = check_file_naming(Path("chapter5.md"), 5)
        assert r.passed is False
        assert r.severity == "hard"


# ---------------------------------------------------------------------------
# check_character_conflicts
# ---------------------------------------------------------------------------

class TestCheckCharacterConflicts:
    def test_no_db(self, tmp_path):
        r = check_character_conflicts("some text", tmp_path)
        assert r.passed is True
        assert "不存在" in r.message

    def test_empty_db(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        # create entities table but leave it empty
        conn.execute("CREATE TABLE entities (name TEXT, type TEXT)")
        conn.execute("CREATE TABLE aliases (alias TEXT)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("some text", tmp_path)
        assert r.passed is True
        assert "为空" in r.message

    def test_with_characters_no_conflict(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE entities (id TEXT, name TEXT, type TEXT, is_protagonist INT DEFAULT 0)")
        conn.execute("INSERT INTO entities VALUES ('zs', '张三', 'character', 0)")
        conn.execute("INSERT INTO entities VALUES ('ls', '李四', 'character', 0)")
        conn.execute("CREATE TABLE aliases (alias TEXT)")
        conn.execute("INSERT INTO aliases VALUES ('老张')")
        conn.execute("CREATE TABLE state_changes (entity_id TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, chapter INT)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("张三和李四在对话", tmp_path)
        assert r.passed is True
        assert "3" in r.message  # 3 known names

    def test_dead_character_detected(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE entities (id TEXT, name TEXT, type TEXT, is_protagonist INT DEFAULT 0)")
        conn.execute("INSERT INTO entities VALUES ('zs', '张三', 'character', 0)")
        conn.execute("INSERT INTO entities VALUES ('ls', '李四', 'character', 0)")
        conn.execute("CREATE TABLE aliases (alias TEXT)")
        conn.execute("CREATE TABLE state_changes (entity_id TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, chapter INT)")
        conn.execute("INSERT INTO state_changes VALUES ('ls', 'status', 'alive', 'dead', '战死', 10)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("张三看着李四走过来，笑着说", tmp_path)
        assert r.passed is False
        assert r.severity == "hard"
        assert "李四" in r.detail

    def test_dead_character_in_recall_ok(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE entities (id TEXT, name TEXT, type TEXT, is_protagonist INT DEFAULT 0)")
        conn.execute("INSERT INTO entities VALUES ('ls', '李四', 'character', 0)")
        conn.execute("CREATE TABLE aliases (alias TEXT)")
        conn.execute("CREATE TABLE state_changes (entity_id TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, chapter INT)")
        conn.execute("INSERT INTO state_changes VALUES ('ls', 'status', 'alive', 'dead', '战死', 10)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("张三回忆起李四当年的音容笑貌", tmp_path)
        assert r.passed is True

    def test_missing_entities_table(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        # no tables at all
        conn.close()

        r = check_character_conflicts("text", tmp_path)
        assert r.passed is True  # gracefully skips

    def test_missing_aliases_table(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE entities (id TEXT, name TEXT, type TEXT, is_protagonist INT DEFAULT 0)")
        conn.execute("INSERT INTO entities VALUES ('zs', '张三', 'character', 0)")
        # no aliases table — should still work gracefully
        conn.commit()
        conn.close()

        r = check_character_conflicts("text", tmp_path)
        assert r.passed is True
        assert "1" in r.message

    def test_db_exception(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        db_path.write_text("not a database")

        r = check_character_conflicts("text", tmp_path)
        assert r.passed is True
        assert "异常" in r.message


# ---------------------------------------------------------------------------
# check_foreshadowing_consistency
# ---------------------------------------------------------------------------

class TestCheckForeshadowing:
    def test_no_db(self, tmp_path):
        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is True
        assert "不存在" in r.message

    def test_no_overdue(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE plot_threads "
            "(thread_id TEXT, planted_chapter INT, expected_payoff_chapter INT, status TEXT)"
        )
        # active but not overdue (expected chapter 45, current 50, delay=5 < 20)
        conn.execute(
            "INSERT INTO plot_threads VALUES ('thread_a', 10, 45, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is True
        assert "通过" in r.message

    def test_overdue_threads(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE plot_threads "
            "(thread_id TEXT, planted_chapter INT, expected_payoff_chapter INT, status TEXT)"
        )
        # severely overdue: expected 10, current 50, delay=40 > 20
        conn.execute(
            "INSERT INTO plot_threads VALUES ('ancient_secret', 5, 10, 'active')"
        )
        conn.execute(
            "INSERT INTO plot_threads VALUES ('lost_sword', 3, 8, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is False
        assert r.severity == "soft"
        assert "2" in r.message
        assert "ancient_secret" in r.detail

    def test_missing_table(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is True

    def test_db_exception(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        db_path.write_text("corrupted")

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is True
        assert "异常" in r.message


# ---------------------------------------------------------------------------
# check_power_level
# ---------------------------------------------------------------------------

class TestCheckPowerLevel:
    def test_no_state_file(self, tmp_path):
        r = check_power_level("text", tmp_path)
        assert r.passed is True
        assert "不存在" in r.message

    def test_realm_present_no_conflict(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {"realm": "筑基期"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("主角修炼中", tmp_path)
        assert r.passed is True
        assert "筑基期" in r.message

    def test_disabled_ability_detected(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {"realm": "金丹期", "disabled_abilities": ["天雷诀"]}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("主角使出天雷诀，雷光大盛", tmp_path)
        assert r.passed is False
        assert r.severity == "hard"
        assert "天雷诀" in r.detail

    def test_lost_item_detected(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {"realm": "金丹期", "lost_items": ["玄铁剑"]}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("主角拔出玄铁剑，寒光闪烁", tmp_path)
        assert r.passed is False
        assert "玄铁剑" in r.detail

    def test_lost_item_in_recall_ok(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {"realm": "金丹期", "lost_items": ["玄铁剑"]}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("他想起失去玄铁剑的那一天", tmp_path)
        assert r.passed is True

    def test_no_realm(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("text", tmp_path)
        assert r.passed is True
        assert "未设置" in r.message

    def test_no_protagonist_key(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_power_level("text", tmp_path)
        assert r.passed is True
        assert "未设置" in r.message

    def test_corrupt_json(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{bad json", encoding="utf-8")

        r = check_power_level("text", tmp_path)
        assert r.passed is True
        assert "异常" in r.message


# ---------------------------------------------------------------------------
# check_contract_completeness
# ---------------------------------------------------------------------------

class TestCheckContract:
    def test_no_state_file(self, tmp_path):
        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is True
        assert "不存在" in r.message

    def test_no_prev_meta(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is True
        assert "不存在" in r.message

    def test_complete_meta(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {"0004": {"hook": "悬念", "ending": "高潮"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is True
        assert "完整" in r.message

    def test_missing_hook(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {"0004": {"ending": "高潮"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is False
        assert "hook" in r.message

    def test_missing_ending(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {"0004": {"hook": "悬念"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is False
        assert "ending" in r.message

    def test_missing_both(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {"0004": {"summary": "foo"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is False
        assert "hook" in r.message
        assert "ending" in r.message

    def test_prev_meta_unpadded_key(self, tmp_path):
        """Should also find prev meta with unpadded key like '4' instead of '0004'."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"chapter_meta": {"4": {"hook": "x", "ending": "y"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is True

    def test_corrupt_json(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("not json", encoding="utf-8")

        r = check_contract_completeness(tmp_path, 5)
        assert r.passed is True
        assert "异常" in r.message


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    def _make_text_with_dialogue(self, narrative_chars=2500, dialogue_count=15):
        """Generate text with adequate dialogue ratio to pass dialogue check."""
        narrative = "叙述" * (narrative_chars // 2)
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(dialogue_count))
        return narrative + dialogues

    def test_all_pass(self, tmp_path):
        chapter_file = Path("第0001章-序幕.md")
        text = self._make_text_with_dialogue()
        result = run_all_checks(tmp_path, 1, chapter_file, text)

        assert result["pass"] is True
        assert result["checks_run"] == 9  # v10.6: +opening_pattern +dialogue_ratio
        assert result["hard_failures"] == []
        assert isinstance(result["all_results"], list)

    def test_hard_failure_propagates(self, tmp_path):
        chapter_file = Path("第0001章.md")
        text = "字" * 10  # too short → hard failure
        result = run_all_checks(tmp_path, 1, chapter_file, text)

        assert result["pass"] is False
        assert len(result["hard_failures"]) >= 1
        assert result["hard_failures"][0]["name"] == "word_count"

    def test_soft_warning_does_not_block(self, tmp_path):
        chapter_file = Path("第0001章.md")
        # Generate text that's over max_words (>5000) but has adequate dialogue
        text = self._make_text_with_dialogue(narrative_chars=4000, dialogue_count=80)
        result = run_all_checks(tmp_path, 1, chapter_file, text)

        assert result["pass"] is True
        assert len(result["soft_warnings"]) >= 1


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_chapter_file(self, tmp_path):
        fake_file = tmp_path / "nonexistent.md"
        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(fake_file)],
        ):
            ret = main()
        assert ret == 1

    def test_json_output_pass(self, tmp_path, capsys):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        chapter_file = tmp_path / "第0001章.md"
        narrative = "叙述" * 1250
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(15))
        chapter_file.write_text(narrative + dialogues, encoding="utf-8")

        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(chapter_file), "--format", "json"],
        ):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["pass"] is True
        assert data["checks_run"] == 9  # v10.6: +opening_pattern +dialogue_ratio

    def test_text_output_pass(self, tmp_path, capsys):
        chapter_file = tmp_path / "第0001章.md"
        narrative = "叙述" * 1250
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(15))
        chapter_file.write_text(narrative + dialogues, encoding="utf-8")

        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(chapter_file), "--format", "text"],
        ):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        assert "全部通过" in out

    def test_text_output_failure(self, tmp_path, capsys):
        chapter_file = tmp_path / "第0001章.md"
        chapter_file.write_text("短", encoding="utf-8")  # too short

        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(chapter_file), "--format", "text"],
        ):
            ret = main()

        assert ret == 1
        out = capsys.readouterr().out
        assert "硬失败" in out

    def test_internal_error_returns_2(self, tmp_path, capsys):
        chapter_file = tmp_path / "第0001章.md"
        narrative = "叙述" * 1250
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(15))
        chapter_file.write_text(narrative + dialogues, encoding="utf-8")

        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(chapter_file)],
        ), patch(
            "computational_checks.run_all_checks",
            side_effect=RuntimeError("boom"),
        ):
            ret = main()

        assert ret == 2
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["pass"] is True
        assert "fallthrough" in data

    def test_text_output_with_soft_warnings(self, tmp_path, capsys):
        chapter_file = tmp_path / "第0001章.md"
        # Generate text > 5000 chars with adequate dialogue ratio
        narrative = "叙述" * 2000
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(80))
        chapter_file.write_text(narrative + dialogues, encoding="utf-8")  # soft warning: too long

        with patch(
            "sys.argv",
            ["prog", "--project-root", str(tmp_path), "--chapter", "1",
             "--chapter-file", str(chapter_file), "--format", "text"],
        ):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        assert "软警告" in out


# ---------------------------------------------------------------------------
# check_dialogue_ratio (v10.6 + tiered thresholds)
# ---------------------------------------------------------------------------

class TestCheckDialogueRatio:
    def test_short_text_skipped(self):
        r = check_dialogue_ratio("短文")
        assert r.passed is True

    def test_zero_dialogue_hard(self):
        text = "字" * 3000
        r = check_dialogue_ratio(text)
        assert r.passed is False
        assert r.severity == "hard"

    def test_low_dialogue_soft(self):
        # ~10% dialogue
        narrative = "叙述文字" * 500  # 2000 chars
        dialogue = "\u201c对话内容对话内容对话内容\u201d" * 10  # ~120 chars dialogue
        text = narrative + dialogue
        r = check_dialogue_ratio(text)
        # ratio ~5-15% → soft warning
        assert r.severity == "soft"

    def test_adequate_dialogue_pass(self):
        # ~40% dialogue
        narrative = "叙述文字" * 200  # 800 chars
        dialogue = "\u201c这是一段对话这是一段对话\u201d" * 80  # ~1200 chars dialogue
        text = narrative + dialogue
        r = check_dialogue_ratio(text)
        assert r.passed is True


# ---------------------------------------------------------------------------
# check_metadata_leakage
# ---------------------------------------------------------------------------

class TestCheckMetadataLeakage:
    def test_clean_text(self):
        r = check_metadata_leakage("这是一段正常的小说正文，没有任何元数据。")
        assert r.passed is True

    def test_leakage_detected(self):
        text = "这是正文" * 200 + "\n\n（本章完）"
        r = check_metadata_leakage(text)
        assert r.passed is False
        assert r.severity == "soft"

    def test_chapter_summary_leakage(self):
        text = "正文内容" * 200 + "\n\n**本章字数：3000**"
        r = check_metadata_leakage(text)
        assert r.passed is False


# ---------------------------------------------------------------------------
# check_opening_pattern
# ---------------------------------------------------------------------------

class TestCheckOpeningPattern:
    def test_action_opening_pass(self):
        r = check_opening_pattern("剑光乍现，萧炎猛然抬头。")
        assert r.passed is True

    def test_time_mark_opening_fail(self):
        r = check_opening_pattern("第三天清晨，萧炎起床了。")
        assert r.passed is False
        assert r.severity == "hard"

    def test_next_day_opening_fail(self):
        r = check_opening_pattern("次日，众人集合。")
        assert r.passed is False

    def test_dialogue_opening_pass(self):
        r = check_opening_pattern("\u201c你来了。\u201d老人抬起头。")
        assert r.passed is True
