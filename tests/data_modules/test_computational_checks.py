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
    check_emotion_punctuation,
    check_file_naming,
    check_first_sentence_hook,
    check_foreshadowing_consistency,
    check_metadata_leakage,
    check_opening_pattern,
    check_power_level,
    check_sentence_length,
    check_vocabulary_diversity,
    check_word_count,
    main,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Helpers — real schema fixtures
# ---------------------------------------------------------------------------

def _create_real_schema(db_path, *, with_state_changes=True):
    """Create tables matching the real index_manager.py schema."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE entities ("
        "  id TEXT PRIMARY KEY, type TEXT NOT NULL, canonical_name TEXT NOT NULL,"
        "  tier TEXT DEFAULT '装饰', desc TEXT, current_json TEXT,"
        "  first_appearance INTEGER, last_appearance INTEGER,"
        "  is_protagonist INTEGER, is_archived INTEGER,"
        "  created_at TIMESTAMP, updated_at TIMESTAMP"
        ")"
    )
    conn.execute(
        "CREATE TABLE aliases ("
        "  alias TEXT NOT NULL, entity_id TEXT NOT NULL, entity_type TEXT NOT NULL,"
        "  created_at TIMESTAMP, PRIMARY KEY(alias, entity_id, entity_type)"
        ")"
    )
    if with_state_changes:
        conn.execute(
            "CREATE TABLE state_changes ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT NOT NULL,"
            "  field TEXT NOT NULL, old_value TEXT, new_value TEXT,"
            "  reason TEXT, chapter INTEGER NOT NULL, created_at TIMESTAMP"
            ")"
        )
    conn.execute(
        "CREATE TABLE plot_thread_registry ("
        "  thread_id TEXT PRIMARY KEY, title TEXT, content TEXT, thread_type TEXT,"
        "  status TEXT, priority INTEGER DEFAULT 50, planted_chapter INTEGER,"
        "  last_touched_chapter INTEGER, target_payoff_chapter INTEGER,"
        "  resolved_chapter INTEGER, related_entities TEXT, notes TEXT,"
        "  confidence REAL, payload_json TEXT, created_at TIMESTAMP, updated_at TIMESTAMP"
        ")"
    )
    conn.commit()
    return conn


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

    def test_hard_failure_too_long_default(self):
        """v23: default max_words_hard=5000，超出即硬失败（替代旧的 soft 警告）."""
        text = "字" * 6000
        r = check_word_count(text)
        assert r.passed is False
        assert r.severity == "hard"
        assert "6000" in r.message

    def test_word_count_hard_upper_limit(self):
        """显式 max_words_hard：超过即硬失败，passed=False."""
        text = "字" * 4500
        r = check_word_count(text, max_words_hard=4000)
        assert r.passed is False
        assert r.severity == "hard"
        assert "4500" in r.message
        assert "4000" in r.message

    def test_word_count_soft_buffer(self):
        """缓冲带：max_words_hard < count <= max_words_soft 返回 soft 警告."""
        text = "字" * 4200  # > 4000, ≤ 4500
        r = check_word_count(text, max_words_hard=4000, max_words_soft=4500)
        assert r.passed is False
        assert r.severity == "soft"
        assert "4200" in r.message

    def test_word_count_soft_buffer_overflow_is_hard(self):
        """超出缓冲带上限 → 硬失败."""
        text = "字" * 4600
        r = check_word_count(text, max_words_hard=4000, max_words_soft=4500)
        assert r.passed is False
        assert r.severity == "hard"

    def test_word_count_backward_compat_max_words_alias(self):
        """deprecated max_words 别名：自动映射到 max_words_hard，行为对齐硬上限."""
        text = "字" * 4800
        r = check_word_count(text, max_words=4500)
        assert r.passed is False
        assert r.severity == "hard"
        assert "4800" in r.message

    def test_markdown_headings_stripped(self):
        heading = "# 第一章 标题\n## 小节\n"
        body = "字" * 2500
        r = check_word_count(heading + body)
        assert r.passed is True

    def test_whitespace_stripped(self):
        text = " 字 " * 2500
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
        conn = _create_real_schema(db_path)
        conn.close()

        r = check_character_conflicts("some text", tmp_path)
        assert r.passed is True
        assert "为空" in r.message

    def test_with_characters_no_conflict(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('zs', '角色', '张三', 0)")
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('ls', '角色', '李四', 0)")
        conn.execute("INSERT INTO aliases (alias, entity_id, entity_type) VALUES ('老张', 'zs', '角色')")
        conn.commit()
        conn.close()

        r = check_character_conflicts("张三和李四在对话", tmp_path)
        assert r.passed is True
        assert "3" in r.message  # 3 known names

    def test_dead_character_detected(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('zs', '角色', '张三', 0)")
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('ls', '角色', '李四', 0)")
        conn.execute("INSERT INTO state_changes (entity_id, field, old_value, new_value, reason, chapter) VALUES ('ls', 'status', 'alive', 'dead', '战死', 10)")
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
        conn = _create_real_schema(db_path)
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('ls', '角色', '李四', 0)")
        conn.execute("INSERT INTO state_changes (entity_id, field, old_value, new_value, reason, chapter) VALUES ('ls', 'status', 'alive', 'dead', '战死', 10)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("张三回忆起李四当年的音容笑貌", tmp_path)
        assert r.passed is True

    def test_dead_character_war_death(self, tmp_path):
        """Test expanded death status matching with '战死' value."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('ww', '角色', '王五', 0)")
        conn.execute("INSERT INTO state_changes (entity_id, field, old_value, new_value, reason, chapter) VALUES ('ww', 'status', 'alive', '战死', '城破之战', 15)")
        conn.commit()
        conn.close()

        r = check_character_conflicts("王五拔剑杀向敌阵", tmp_path)
        assert r.passed is False
        assert r.severity == "hard"
        assert "王五" in r.detail

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
        conn.execute(
            "CREATE TABLE entities ("
            "  id TEXT PRIMARY KEY, type TEXT NOT NULL, canonical_name TEXT NOT NULL,"
            "  is_protagonist INTEGER"
            ")"
        )
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('zs', '角色', '张三', 0)")
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
        db_path.write_text("not a database", encoding="utf-8")

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
        conn = _create_real_schema(db_path)
        # active but not overdue (target chapter 45, current 50, delay=5 < 20)
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('thread_a', 10, 45, 'active')"
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
        conn = _create_real_schema(db_path)
        # severely overdue: target 10, current 50, delay=40 > 20
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('ancient_secret', 5, 10, 'active')"
        )
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('lost_sword', 3, 8, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is False
        assert r.severity == "hard"  # delay 40/42 > 30 → hard
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
        db_path.write_text("corrupted", encoding="utf-8")

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

    def test_power_level_broader_field_match(self, tmp_path):
        """Test that broader field LIKE matching catches Chinese field names."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        state = {"protagonist": {"power": {"realm": "金丹期"}}}
        (ink_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        conn.execute("INSERT INTO entities (id, type, canonical_name, is_protagonist) VALUES ('mc', '角色', '主角', 1)")
        conn.execute(
            "INSERT INTO state_changes (entity_id, field, old_value, new_value, reason, chapter) "
            "VALUES ('mc', '封印能力', '破天掌', '已封印', '被长老封印', 20)"
        )
        conn.commit()
        conn.close()

        r = check_power_level("主角运起破天掌，掌风呼啸", tmp_path)
        assert r.passed is False
        assert "破天掌" in r.detail


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
        assert result["checks_run"] == 13  # 11 original + vocabulary_diversity + first_sentence_hook
        assert result["hard_failures"] == []
        assert isinstance(result["all_results"], list)

    def test_hard_failure_propagates(self, tmp_path):
        chapter_file = Path("第0001章.md")
        text = "字" * 10  # too short -> hard failure
        result = run_all_checks(tmp_path, 1, chapter_file, text)

        assert result["pass"] is False
        assert len(result["hard_failures"]) >= 1
        assert result["hard_failures"][0]["name"] == "word_count"

    def test_soft_warning_does_not_block(self, tmp_path):
        chapter_file = Path("第0001章.md")
        # v23: 字数硬上限收紧后，依靠 vocab/emotion 等检查产出软警告即可，
        # 字数本身保持在 ≤5000 硬上限内。
        text = self._make_text_with_dialogue(narrative_chars=3600, dialogue_count=60)
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
        assert data["checks_run"] == 13  # updated count

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
        # v23: 字数硬上限收紧后，依靠词汇多样性/情感标点等检查产生软警告。
        narrative = "叙述" * 1800  # 3600 chars，触发 vocab/emotion soft 警告
        dialogues = "".join(f"\u201c角色对话内容第{i}句话\u201d" for i in range(60))
        chapter_file.write_text(narrative + dialogues, encoding="utf-8")

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
        # ratio ~5-15% -> soft warning
        assert r.severity == "soft"

    def test_adequate_dialogue_pass(self):
        # ~40% dialogue
        narrative = "叙述文字" * 200  # 800 chars
        dialogue = "\u201c这是一段对话这是一段对话\u201d" * 80  # ~1200 chars dialogue
        text = narrative + dialogue
        r = check_dialogue_ratio(text)
        assert r.passed is True

    def test_dialogue_with_book_quotes(self):
        """Test that 「」 quotes are also counted as dialogue."""
        narrative = "叙述文字" * 200  # 800 chars
        dialogue = "\u300c这是一段对话这是一段对话\u300d" * 80  # ~1200 chars using 「」
        text = narrative + dialogue
        r = check_dialogue_ratio(text)
        assert r.passed is True

    def test_dialogue_mixed_quotes(self):
        """Test mixed "" and 「」 quotes are both counted."""
        narrative = "叙述文字" * 200  # 800 chars
        dialogue_cn = "\u201c这是一段中文引号对话\u201d" * 40
        dialogue_jp = "\u300c这是一段书名号对话内容\u300d" * 40
        text = narrative + dialogue_cn + dialogue_jp
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

    def test_metadata_in_middle(self):
        """Test that metadata in the middle of text is also detected (full-text scan)."""
        text = "正文内容" * 100 + "\n\n（作者按）这里有批注\n\n" + "正文内容" * 100
        r = check_metadata_leakage(text)
        assert r.passed is False
        assert r.severity == "soft"

    def test_summary_heading_detected(self):
        """Test that ## Summary heading is detected as metadata."""
        text = "正文内容" * 100 + "\n## Summary\n这是总结\n" + "正文内容" * 100
        r = check_metadata_leakage(text)
        assert r.passed is False

    def test_todo_comment_detected(self):
        """Test that // TODO is detected as metadata."""
        text = "正文内容" * 100 + "\n// TODO fix this\n" + "正文内容" * 100
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


# ---------------------------------------------------------------------------
# check_sentence_length
# ---------------------------------------------------------------------------

class TestCheckSentenceLength:
    def test_sentence_length_fragmented(self):
        """Sentences too short (avg < 15 chars)."""
        # Generate many short sentences: "短句子。" = 3 chars per sentence
        text = "短句子。" * 50
        r = check_sentence_length(text)
        assert r.passed is False
        assert r.severity == "soft"
        assert "碎片化" in r.message

    def test_sentence_length_normal(self):
        """Sentences within normal range."""
        # Each sentence ~25 chars
        sentence = "这是一个正常长度的句子用来测试句长均值是否在合理范围内"  # ~25 chars
        text = (sentence + "。") * 30
        r = check_sentence_length(text)
        assert r.passed is True

    def test_sentence_length_too_long(self):
        """Sentences too long (avg > 45 chars)."""
        long_sentence = "这" * 50
        text = (long_sentence + "。") * 15
        r = check_sentence_length(text)
        assert r.passed is False
        assert "过长" in r.message

    def test_sentence_length_too_few_sentences(self):
        """Less than 10 sentences should be skipped."""
        text = "短句。" * 5
        r = check_sentence_length(text)
        assert r.passed is True
        assert "不足" in r.message


# ---------------------------------------------------------------------------
# check_emotion_punctuation
# ---------------------------------------------------------------------------

class TestCheckEmotionPunctuation:
    def test_emotion_punctuation_low(self):
        """No punctuation at all -> low density."""
        text = "这是一段没有任何感叹号问号省略号的正文内容" * 100  # ~2000 chars, no ! or ?
        r = check_emotion_punctuation(text)
        assert r.passed is False
        assert r.severity == "soft"
        assert "偏低" in r.message

    def test_emotion_punctuation_normal(self):
        """Adequate punctuation density."""
        base = "叙述内容" * 50  # ~200 chars
        excl = "太好了！" * 5   # 5 exclamation marks
        ques = "真的吗？" * 5   # 5 question marks
        text = base + excl + ques
        # total ~250 chars; need >= 1000 chars
        text = text * 5  # ~1250 chars, 25 ! and 25 ?
        r = check_emotion_punctuation(text)
        assert r.passed is True

    def test_emotion_punctuation_short_text(self):
        """Text < 1000 chars should be skipped."""
        text = "短文"
        r = check_emotion_punctuation(text)
        assert r.passed is True
        assert "过短" in r.message


# ---------------------------------------------------------------------------
# check_vocabulary_diversity
# ---------------------------------------------------------------------------

class TestCheckVocabularyDiversity:
    def test_diverse_text_pass(self):
        """Diverse text with many unique bigrams should pass."""
        # Use a wide variety of characters to ensure high TTR
        import random
        random.seed(42)
        # Generate 600 distinct characters from CJK range
        chars = [chr(c) for c in range(0x4e00, 0x4e00 + 800)]
        random.shuffle(chars)
        text = "".join(chars)
        r = check_vocabulary_diversity(text)
        assert r.passed is True
        assert "TTR=" in r.message

    def test_repetitive_text_fail(self):
        """Highly repetitive text should fail TTR check."""
        # "叙述" repeated 500 times = 1000 chars, only 1 unique bigram "叙述"
        text = "叙述" * 500
        r = check_vocabulary_diversity(text)
        assert r.passed is False
        assert r.severity == "soft"
        assert "重复" in r.message

    def test_short_text_skip(self):
        """Text with < 500 Chinese chars should be skipped."""
        text = "短文" * 10  # 20 chars
        r = check_vocabulary_diversity(text)
        assert r.passed is True
        assert "过短" in r.message


# ---------------------------------------------------------------------------
# check_first_sentence_hook
# ---------------------------------------------------------------------------

class TestCheckFirstSentenceHook:
    def test_dialogue_opening_pass(self):
        r = check_first_sentence_hook("\u201c你是谁？\u201d他警惕地后退一步。")
        assert r.passed is True
        assert "钩子特征" in r.message

    def test_action_opening_pass(self):
        r = check_first_sentence_hook("他猛地从床上跳起来。")
        assert r.passed is True

    def test_explanatory_opening_fail(self):
        r = check_first_sentence_hook("这是一个普通的早晨。")
        assert r.passed is False
        assert r.severity == "soft"
        assert "说明性" in r.message

    def test_empty_text(self):
        r = check_first_sentence_hook("")
        assert r.passed is True
        assert "为空" in r.message

    def test_sensory_opening_pass(self):
        r = check_first_sentence_hook("血光冲天而起，照亮了半边夜空。")
        assert r.passed is True


# ---------------------------------------------------------------------------
# check_foreshadowing_consistency (tiered)
# ---------------------------------------------------------------------------

class TestCheckForeshadowingTiered:
    def test_overdue_10_info(self, tmp_path):
        """Delay 11 chapters -> info level (passed=True)."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        # target=39, current=50, delay=11 > 10
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('thread_info', 10, 39, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is True
        assert r.severity == "soft"
        assert "接近逾期" in r.message

    def test_overdue_20_soft(self, tmp_path):
        """Delay 21 chapters -> soft warning (passed=False, severity=soft)."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        # target=29, current=50, delay=21 > 20
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('thread_soft', 5, 29, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is False
        assert r.severity == "soft"
        assert "逾期" in r.message

    def test_overdue_30_hard(self, tmp_path):
        """Delay 31 chapters -> hard failure (passed=False, severity=hard)."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        db_path = ink_dir / "index.db"
        conn = _create_real_schema(db_path)
        # target=19, current=50, delay=31 > 30
        conn.execute(
            "INSERT INTO plot_thread_registry (thread_id, planted_chapter, target_payoff_chapter, status) "
            "VALUES ('thread_hard', 3, 19, 'active')"
        )
        conn.commit()
        conn.close()

        r = check_foreshadowing_consistency(tmp_path, 50)
        assert r.passed is False
        assert r.severity == "hard"
        assert "严重逾期" in r.detail


# ---------------------------------------------------------------------------
# check_emotion_punctuation (aligned threshold)
# ---------------------------------------------------------------------------

class TestCheckEmotionPunctuationAligned:
    def test_below_1_per_k_warning(self):
        """Exclamation marks at 0.8/k should trigger soft warning with new threshold."""
        # Build ~2500 chars with only 2 exclamation marks and plenty of questions
        base = "叙述内容文字" * 400  # 2400 chars
        excl = "啊！"  # 1 exclamation mark in ~2500 chars => 0.4/k
        ques = "吗？" * 10  # 10 question marks => ~4/k (above threshold)
        text = base + excl + ques
        r = check_emotion_punctuation(text)
        assert r.passed is False
        assert r.severity == "soft"
