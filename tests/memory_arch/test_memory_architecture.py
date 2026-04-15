#!/usr/bin/env python3
"""
Tests for US-301: 单一事实源架构 (Memory Architecture v13)

验证:
1. state_kv CRUD
2. disambiguation_log CRUD
3. review_checkpoint_entries CRUD
4. rebuild_state_dict 往返一致性
5. migrate_state_to_kv 迁移正确性
6. StateManager 从 SQLite 重建
7. migration v8→v9
"""

import json
import shutil
from pathlib import Path

import pytest

from data_modules.config import DataModulesConfig
from data_modules.sql_state_manager import SQLStateManager
from data_modules.index_manager import IndexManager
from data_modules.state_manager import StateManager


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def sql_mgr(temp_project):
    return SQLStateManager(temp_project)


# ==================== state_kv CRUD ====================


class TestStateKV:
    def test_set_and_get(self, sql_mgr):
        sql_mgr.set_state_kv("project_info", {"title": "测试小说", "genre": "玄幻"})
        result = sql_mgr.get_state_kv("project_info")
        assert result["title"] == "测试小说"
        assert result["genre"] == "玄幻"

    def test_get_nonexistent_returns_default(self, sql_mgr):
        assert sql_mgr.get_state_kv("missing") is None
        assert sql_mgr.get_state_kv("missing", {"default": True}) == {"default": True}

    def test_overwrite(self, sql_mgr):
        sql_mgr.set_state_kv("progress", {"current_chapter": 1})
        sql_mgr.set_state_kv("progress", {"current_chapter": 42})
        assert sql_mgr.get_state_kv("progress")["current_chapter"] == 42

    def test_get_all(self, sql_mgr):
        sql_mgr.set_state_kv("a", 1)
        sql_mgr.set_state_kv("b", "two")
        sql_mgr.set_state_kv("c", [3])
        all_kv = sql_mgr.get_all_state_kv()
        assert all_kv["a"] == 1
        assert all_kv["b"] == "two"
        assert all_kv["c"] == [3]

    def test_delete(self, sql_mgr):
        sql_mgr.set_state_kv("temp", "value")
        assert sql_mgr.delete_state_kv("temp") is True
        assert sql_mgr.get_state_kv("temp") is None
        assert sql_mgr.delete_state_kv("nonexistent") is False

    def test_bulk_set(self, sql_mgr):
        entries = {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 5},
            "schema_version": 9,
        }
        count = sql_mgr.bulk_set_state_kv(entries)
        assert count == 3
        assert sql_mgr.get_state_kv("schema_version") == 9

    def test_unicode_values(self, sql_mgr):
        sql_mgr.set_state_kv("protagonist_state", {
            "name": "萧炎",
            "power": {"realm": "斗帝", "layer": 9},
        })
        result = sql_mgr.get_state_kv("protagonist_state")
        assert result["name"] == "萧炎"
        assert result["power"]["realm"] == "斗帝"


# ==================== disambiguation_log CRUD ====================


class TestDisambiguationLog:
    def test_add_and_get_warning(self, sql_mgr):
        entry_id = sql_mgr.add_disambiguation_entry(
            "warning",
            {"chapter": 5, "mention": "萧炎", "chosen_id": "xiaoyan", "confidence": 0.8},
            chapter=5,
        )
        assert entry_id > 0
        warnings = sql_mgr.get_disambiguation_entries("warning")
        assert len(warnings) == 1
        assert warnings[0]["mention"] == "萧炎"

    def test_add_and_get_pending(self, sql_mgr):
        sql_mgr.add_disambiguation_entry(
            "pending",
            {"chapter": 3, "mention": "红衣女子", "suggested_id": "hongyi"},
            chapter=3,
        )
        pending = sql_mgr.get_disambiguation_entries("pending")
        assert len(pending) == 1
        assert pending[0]["suggested_id"] == "hongyi"

    def test_resolve(self, sql_mgr):
        entry_id = sql_mgr.add_disambiguation_entry("warning", {"test": True})
        assert sql_mgr.resolve_disambiguation_entry(entry_id) is True
        assert len(sql_mgr.get_disambiguation_entries("warning", status="active")) == 0
        resolved = sql_mgr.get_disambiguation_entries("warning", status="resolved")
        assert len(resolved) == 1

    def test_bulk_add(self, sql_mgr):
        payloads = [{"i": i} for i in range(5)]
        count = sql_mgr.bulk_add_disambiguation_entries("warning", payloads, chapter=1)
        assert count == 5
        assert len(sql_mgr.get_disambiguation_entries("warning")) == 5

    def test_category_isolation(self, sql_mgr):
        sql_mgr.add_disambiguation_entry("warning", {"w": 1})
        sql_mgr.add_disambiguation_entry("pending", {"p": 1})
        assert len(sql_mgr.get_disambiguation_entries("warning")) == 1
        assert len(sql_mgr.get_disambiguation_entries("pending")) == 1


# ==================== review_checkpoint_entries CRUD ====================


class TestReviewCheckpoints:
    def test_add_and_get(self, sql_mgr):
        ckpt_id = sql_mgr.add_review_checkpoint({"chapter_range": "1-10", "score": 85})
        assert ckpt_id > 0
        checkpoints = sql_mgr.get_review_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]["score"] == 85

    def test_ordering(self, sql_mgr):
        for i in range(5):
            sql_mgr.add_review_checkpoint({"index": i})
        result = sql_mgr.get_review_checkpoints()
        assert len(result) == 5
        # Entries returned in insertion order (by id ascending)
        indices = [r["index"] for r in result]
        assert indices == sorted(indices)

    def test_bulk_add(self, sql_mgr):
        payloads = [{"chapter": i} for i in range(3)]
        count = sql_mgr.bulk_add_review_checkpoints(payloads)
        assert count == 3
        assert len(sql_mgr.get_review_checkpoints()) == 3


# ==================== rebuild_state_dict ====================


class TestRebuildStateDict:
    def _make_full_state(self):
        return {
            "schema_version": 9,
            "project_info": {"title": "测试小说", "genre": "玄幻"},
            "progress": {"current_chapter": 50, "total_words": 100000},
            "protagonist_state": {
                "name": "萧炎",
                "power": {"realm": "斗帝", "layer": 9, "bottleneck": ""},
                "location": {"current": "中州", "last_chapter": 50},
                "golden_finger": {"name": "异火", "level": 5, "cooldown": 0, "skills": []},
                "attributes": {},
            },
            "relationships": {"萧炎-药老": "师徒"},
            "disambiguation_warnings": [{"chapter": 5, "mention": "他"}],
            "disambiguation_pending": [{"chapter": 3, "mention": "红衣"}],
            "world_settings": {
                "power_system": [{"name": "斗气"}],
                "factions": [{"name": "天云宗"}],
                "locations": [{"name": "中州"}],
            },
            "plot_threads": {"active_threads": [], "foreshadowing": []},
            "review_checkpoints": [{"chapter_range": "1-10"}],
            "chapter_meta": {},
            "strand_tracker": {
                "last_quest_chapter": 45,
                "last_fire_chapter": 48,
                "last_constellation_chapter": 40,
                "current_dominant": "fire",
                "chapters_since_switch": 2,
                "history": [],
            },
            "harness_config": {"computational_gate_enabled": True},
            "hook_contract_config": {"enabled": True, "valid_types": ["crisis"]},
        }

    def test_migrate_and_rebuild_roundtrip(self, sql_mgr):
        original = self._make_full_state()
        sql_mgr.migrate_state_to_kv(original)

        rebuilt = sql_mgr.rebuild_state_dict()

        assert rebuilt["schema_version"] == 9
        assert rebuilt["project_info"]["title"] == "测试小说"
        assert rebuilt["progress"]["current_chapter"] == 50
        assert rebuilt["protagonist_state"]["name"] == "萧炎"
        assert rebuilt["protagonist_state"]["power"]["realm"] == "斗帝"
        assert rebuilt["relationships"] == original["relationships"]
        assert rebuilt["world_settings"]["power_system"] == [{"name": "斗气"}]
        assert rebuilt["strand_tracker"]["current_dominant"] == "fire"
        assert rebuilt["harness_config"]["computational_gate_enabled"] is True
        assert rebuilt["hook_contract_config"]["valid_types"] == ["crisis"]

    def test_rebuild_disambiguation_data(self, sql_mgr):
        original = self._make_full_state()
        sql_mgr.migrate_state_to_kv(original)

        rebuilt = sql_mgr.rebuild_state_dict()
        assert len(rebuilt["disambiguation_warnings"]) == 1
        assert rebuilt["disambiguation_warnings"][0]["mention"] == "他"
        assert len(rebuilt["disambiguation_pending"]) == 1
        assert rebuilt["disambiguation_pending"][0]["mention"] == "红衣"

    def test_rebuild_review_checkpoints(self, sql_mgr):
        original = self._make_full_state()
        sql_mgr.migrate_state_to_kv(original)

        rebuilt = sql_mgr.rebuild_state_dict()
        assert len(rebuilt["review_checkpoints"]) == 1
        assert rebuilt["review_checkpoints"][0]["chapter_range"] == "1-10"

    def test_rebuild_empty_state(self, sql_mgr):
        rebuilt = sql_mgr.rebuild_state_dict()
        assert rebuilt["schema_version"] == 9
        assert rebuilt["project_info"] == {}
        assert rebuilt["disambiguation_warnings"] == []
        assert rebuilt["review_checkpoints"] == []

    def test_rebuild_state_json_writes_file(self, sql_mgr, temp_project):
        sql_mgr.set_state_kv("project_info", {"title": "文件测试"})
        sql_mgr.set_state_kv("schema_version", 9)

        state = sql_mgr.rebuild_state_json()
        assert temp_project.state_file.exists()

        on_disk = json.loads(temp_project.state_file.read_text(encoding="utf-8"))
        assert on_disk["project_info"]["title"] == "文件测试"


# ==================== migrate_state_to_kv ====================


class TestMigrateStateToKV:
    def test_migrate_counts(self, sql_mgr):
        state = {
            "schema_version": 9,
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 1},
            "disambiguation_warnings": [{"w": 1}, {"w": 2}],
            "disambiguation_pending": [{"p": 1}],
            "review_checkpoints": [{"c": 1}, {"c": 2}, {"c": 3}],
        }
        count = sql_mgr.migrate_state_to_kv(state)
        # 3 kv entries (schema_version, project_info, progress) + 2 warnings + 1 pending + 3 checkpoints = 9
        assert count == 9

    def test_migrate_idempotent(self, sql_mgr):
        state = {"schema_version": 9, "project_info": {"title": "Test"}}
        sql_mgr.migrate_state_to_kv(state)
        sql_mgr.migrate_state_to_kv(state)
        assert sql_mgr.get_state_kv("project_info")["title"] == "Test"


# ==================== StateManager integration ====================


class TestStateManagerIntegration:
    def test_state_manager_syncs_to_kv(self, temp_project):
        state_file = temp_project.state_file
        state_file.write_text(json.dumps({
            "schema_version": 9,
            "project_info": {"title": "同步测试"},
            "progress": {"current_chapter": 0, "total_words": 0},
            "protagonist_state": {},
            "relationships": {},
            "world_settings": {"power_system": [], "factions": [], "locations": []},
            "plot_threads": {"active_threads": [], "foreshadowing": []},
            "review_checkpoints": [],
            "chapter_meta": {},
            "strand_tracker": {
                "last_quest_chapter": 0, "last_fire_chapter": 0,
                "last_constellation_chapter": 0, "current_dominant": "quest",
                "chapters_since_switch": 0, "history": [],
            },
        }, ensure_ascii=False), encoding="utf-8")

        sm = StateManager(temp_project, enable_sqlite_sync=True)
        sm.update_progress(chapter=5, words=3000)
        sm.save_state()

        sql_mgr = SQLStateManager(temp_project)
        progress = sql_mgr.get_state_kv("progress")
        assert progress is not None
        assert progress["current_chapter"] == 5

    def test_state_manager_rebuilds_from_sqlite(self, temp_project):
        sql_mgr = SQLStateManager(temp_project)
        sql_mgr.bulk_set_state_kv({
            "schema_version": 9,
            "project_info": {"title": "重建测试", "genre": "仙侠"},
            "progress": {"current_chapter": 100, "total_words": 200000},
            "protagonist_state": {"name": "顾望安"},
            "world_settings": {"power_system": [], "factions": [], "locations": []},
            "strand_tracker": {
                "last_quest_chapter": 0, "last_fire_chapter": 0,
                "last_constellation_chapter": 0, "current_dominant": "quest",
                "chapters_since_switch": 0, "history": [],
            },
        })

        assert not temp_project.state_file.exists()

        sm = StateManager(temp_project, enable_sqlite_sync=True)
        assert sm._state["project_info"]["title"] == "重建测试"
        assert sm._state["progress"]["current_chapter"] == 100


# ==================== Migration v8→v9 ====================


class TestMigrationV8toV9:
    def test_v8_to_v9_schema_migration(self, tmp_path):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))
        from migrate import run_migrations, CURRENT_SCHEMA_VERSION

        project_root = tmp_path / "test_project"
        ink_dir = project_root / ".ink"
        ink_dir.mkdir(parents=True)

        state_v8 = {
            "schema_version": 8,
            "project_info": {"title": "迁移测试"},
            "progress": {"current_chapter": 30},
            "protagonist_state": {"name": "测试主角"},
            "hook_contract_config": {"enabled": True},
        }
        state_file = ink_dir / "state.json"
        state_file.write_text(json.dumps(state_v8, ensure_ascii=False), encoding="utf-8")

        result = run_migrations(state_file)
        assert result["schema_version"] == CURRENT_SCHEMA_VERSION
        assert result.get("_migrated_to_single_source") is True

    def test_v9_already_migrated_skips(self, tmp_path):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))
        from migrate import run_migrations

        project_root = tmp_path / "test_project"
        ink_dir = project_root / ".ink"
        ink_dir.mkdir(parents=True)

        state_v9 = {"schema_version": 9, "project_info": {"title": "Already v9"}}
        state_file = ink_dir / "state.json"
        state_file.write_text(json.dumps(state_v9, ensure_ascii=False), encoding="utf-8")

        result = run_migrations(state_file)
        assert result["schema_version"] == 9

    def test_full_migration_with_sqlite_sync(self, tmp_path):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))
        from migrate import migrate_state_to_sqlite

        project_root = tmp_path / "test_project"
        ink_dir = project_root / ".ink"
        ink_dir.mkdir(parents=True)

        state = {
            "schema_version": 9,
            "project_info": {"title": "全量迁移测试"},
            "progress": {"current_chapter": 50},
            "disambiguation_warnings": [{"warn": 1}],
            "review_checkpoints": [{"ckpt": 1}],
        }
        state_file = ink_dir / "state.json"
        state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        migrate_state_to_sqlite(state_file, project_root)

        cfg = DataModulesConfig.from_project_root(project_root)
        sql_mgr = SQLStateManager(cfg)
        assert sql_mgr.get_state_kv("project_info")["title"] == "全量迁移测试"
        assert len(sql_mgr.get_disambiguation_entries("warning")) == 1
        assert len(sql_mgr.get_review_checkpoints()) == 1


# ==================== Tables exist ====================


class TestTablesExist:
    def test_new_tables_created(self, temp_project):
        im = IndexManager(temp_project)
        with im._get_conn() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "state_kv" in tables
        assert "disambiguation_log" in tables
        assert "review_checkpoint_entries" in tables
