#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StateManager unit tests

Covers: init, schema defaults, load/save, progress, entity CRUD,
        state changes, relationships, export_for_context, file locking.
"""

import json
import sys
from pathlib import Path

import pytest

from data_modules.config import DataModulesConfig
from data_modules.state_manager import StateManager, EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config(tmp_path):
    """Create a minimal project config with .ink dir."""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    cfg = DataModulesConfig.from_project_root(tmp_path)
    return cfg


@pytest.fixture
def state_mgr(config):
    """StateManager with no SQLite sync and an empty state file."""
    return StateManager(config, enable_sqlite_sync=False)


@pytest.fixture
def state_mgr_with_data(config):
    """StateManager initialised from a pre-populated state.json."""
    state = {
        "progress": {"current_chapter": 5, "total_words": 10000},
        "project_info": {"title": "测试书"},
        "protagonist_state": {"name": "萧尘"},
    }
    config.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return StateManager(config, enable_sqlite_sync=False)


# ---------------------------------------------------------------------------
# 1. __init__ basics
# ---------------------------------------------------------------------------

def test_init_creates_default_state(state_mgr):
    """Init without existing state.json should produce a valid default state."""
    s = state_mgr._state
    assert isinstance(s, dict)
    assert "progress" in s
    assert "project_info" in s
    assert s["progress"]["current_chapter"] == 0
    assert s["progress"]["total_words"] == 0


def test_init_loads_existing_state(state_mgr_with_data):
    """Init should load pre-existing state.json content."""
    assert state_mgr_with_data._state["progress"]["current_chapter"] == 5
    assert state_mgr_with_data._state["progress"]["total_words"] == 10000
    assert state_mgr_with_data._state["project_info"]["title"] == "测试书"


def test_init_sqlite_sync_disabled(state_mgr):
    """enable_sqlite_sync=False should leave _sql_state_manager as None."""
    assert state_mgr._enable_sqlite_sync is False
    assert state_mgr._sql_state_manager is None


# ---------------------------------------------------------------------------
# 2. _ensure_state_schema
# ---------------------------------------------------------------------------

def test_ensure_state_schema_adds_missing_fields(state_mgr):
    """_ensure_state_schema should add all required default keys."""
    result = state_mgr._ensure_state_schema({})
    for key in [
        "project_info", "progress", "protagonist_state",
        "relationships", "world_settings", "plot_threads",
        "review_checkpoints", "chapter_meta", "strand_tracker",
        "disambiguation_warnings", "disambiguation_pending",
        "latest_warnings",
    ]:
        assert key in result, f"Missing default key: {key}"


def test_ensure_state_schema_preserves_existing(state_mgr):
    """Existing values should not be overwritten by defaults."""
    state = {"project_info": {"title": "My Book"}, "progress": {"current_chapter": 42}}
    result = state_mgr._ensure_state_schema(state)
    assert result["project_info"]["title"] == "My Book"
    assert result["progress"]["current_chapter"] == 42


def test_ensure_state_schema_migrates_list_relationships(state_mgr):
    """If relationships is a list, it should migrate to structured_relationships."""
    state = {"relationships": [{"from_entity": "a", "to_entity": "b"}]}
    result = state_mgr._ensure_state_schema(state)
    assert isinstance(result["relationships"], dict)
    assert isinstance(result.get("structured_relationships"), list)
    assert len(result["structured_relationships"]) == 1


def test_ensure_state_schema_handles_non_dict_input(state_mgr):
    """Passing None or a non-dict should produce a valid state."""
    result = state_mgr._ensure_state_schema(None)
    assert isinstance(result, dict)
    assert "progress" in result


# ---------------------------------------------------------------------------
# 3. _load_state
# ---------------------------------------------------------------------------

def test_load_state_creates_defaults_when_no_file(config):
    """When state.json does not exist, defaults are created in memory."""
    config.state_file.unlink(missing_ok=True)
    mgr = StateManager(config, enable_sqlite_sync=False)
    assert mgr._state["progress"]["current_chapter"] == 0


def test_load_state_reads_file(config):
    """When state.json exists, it is read and schema-ensured."""
    state = {"progress": {"current_chapter": 7}}
    config.state_file.write_text(json.dumps(state), encoding="utf-8")
    mgr = StateManager(config, enable_sqlite_sync=False)
    assert mgr._state["progress"]["current_chapter"] == 7


# ---------------------------------------------------------------------------
# 4. Progress management (get_current_chapter / update_progress)
# ---------------------------------------------------------------------------

def test_get_current_chapter_default(state_mgr):
    assert state_mgr.get_current_chapter() == 0


def test_update_progress_chapter(state_mgr):
    state_mgr.update_progress(chapter=3, words=2000)
    assert state_mgr.get_current_chapter() == 3
    assert state_mgr._state["progress"]["total_words"] == 2000
    assert state_mgr._pending_progress_chapter == 3
    assert state_mgr._pending_progress_words_delta == 2000


def test_update_progress_chapter_takes_max(state_mgr):
    """Multiple update_progress calls should keep the max chapter."""
    state_mgr.update_progress(chapter=5)
    state_mgr.update_progress(chapter=3)
    assert state_mgr._pending_progress_chapter == 5


def test_update_progress_words_accumulate(state_mgr):
    """Word counts should accumulate across calls."""
    state_mgr.update_progress(chapter=1, words=1000)
    state_mgr.update_progress(chapter=2, words=1500)
    assert state_mgr._pending_progress_words_delta == 2500


# ---------------------------------------------------------------------------
# 5. Entity CRUD (add / get / update)
# ---------------------------------------------------------------------------

def test_add_entity(state_mgr):
    entity = EntityState(id="xiaochen", name="萧尘", type="角色", tier="核心")
    assert state_mgr.add_entity(entity) is True


def test_add_entity_duplicate_returns_false(state_mgr):
    entity = EntityState(id="xiaochen", name="萧尘", type="角色")
    state_mgr.add_entity(entity)
    assert state_mgr.add_entity(entity) is False


def test_get_entity_by_id(state_mgr):
    entity = EntityState(id="xiaochen", name="萧尘", type="角色", tier="核心")
    state_mgr.add_entity(entity)
    result = state_mgr.get_entity("xiaochen")
    assert result is not None
    assert result["canonical_name"] == "萧尘"
    assert result["tier"] == "核心"


def test_get_entity_not_found(state_mgr):
    assert state_mgr.get_entity("nonexistent") is None


def test_get_entity_with_type(state_mgr):
    entity = EntityState(id="loc1", name="青山城", type="地点")
    state_mgr.add_entity(entity)
    assert state_mgr.get_entity("loc1", entity_type="地点") is not None
    # Wrong type should return None
    assert state_mgr.get_entity("loc1", entity_type="角色") is None


def test_update_entity_current(state_mgr):
    entity = EntityState(id="xiaochen", name="萧尘", type="角色")
    state_mgr.add_entity(entity)
    state_mgr.update_entity("xiaochen", {"current": {"realm": "斗师"}})
    e = state_mgr.get_entity("xiaochen")
    assert e["current"]["realm"] == "斗师"


def test_update_entity_nonexistent_returns_false(state_mgr):
    assert state_mgr.update_entity("ghost", {"current": {"x": 1}}) is False


def test_get_all_entities(state_mgr):
    state_mgr.add_entity(EntityState(id="a", name="A", type="角色"))
    state_mgr.add_entity(EntityState(id="b", name="B", type="地点"))
    all_ents = state_mgr.get_all_entities()
    assert "a" in all_ents
    assert "b" in all_ents
    assert all_ents["a"]["type"] == "角色"
    assert all_ents["b"]["type"] == "地点"


def test_get_entities_by_type(state_mgr):
    state_mgr.add_entity(EntityState(id="c1", name="C1", type="角色"))
    state_mgr.add_entity(EntityState(id="c2", name="C2", type="角色"))
    state_mgr.add_entity(EntityState(id="l1", name="L1", type="地点"))
    chars = state_mgr.get_entities_by_type("角色")
    assert "c1" in chars
    assert "c2" in chars
    assert "l1" not in chars


def test_get_entity_type(state_mgr):
    state_mgr.add_entity(EntityState(id="w1", name="剑", type="物品"))
    assert state_mgr.get_entity_type("w1") == "物品"
    assert state_mgr.get_entity_type("missing") is None


# ---------------------------------------------------------------------------
# 6. update_entity_appearance
# ---------------------------------------------------------------------------

def test_update_entity_appearance(state_mgr):
    state_mgr.add_entity(EntityState(id="xiaochen", name="萧尘", type="角色"))
    state_mgr.update_entity_appearance("xiaochen", chapter=3, entity_type="角色")
    e = state_mgr.get_entity("xiaochen")
    assert e["first_appearance"] == 3
    assert e["last_appearance"] == 3

    state_mgr.update_entity_appearance("xiaochen", chapter=10, entity_type="角色")
    e = state_mgr.get_entity("xiaochen")
    assert e["first_appearance"] == 3
    assert e["last_appearance"] == 10


# ---------------------------------------------------------------------------
# 7. State changes
# ---------------------------------------------------------------------------

def test_record_state_change(state_mgr):
    state_mgr.add_entity(EntityState(id="xiaochen", name="萧尘", type="角色"))
    state_mgr.record_state_change(
        entity_id="xiaochen",
        field="realm",
        old_value="凡人",
        new_value="斗者",
        reason="突破",
        chapter=1,
    )
    changes = state_mgr.get_state_changes("xiaochen")
    assert len(changes) == 1
    assert changes[0]["field"] == "realm"
    assert changes[0]["new_value"] == "斗者"
    # The entity's attributes should also be updated
    e = state_mgr.get_entity("xiaochen")
    assert e["current"]["realm"] == "斗者"


def test_get_state_changes_all(state_mgr):
    state_mgr.add_entity(EntityState(id="a", name="A", type="角色"))
    state_mgr.add_entity(EntityState(id="b", name="B", type="角色"))
    state_mgr.record_state_change("a", "realm", "1", "2", "升级", 1)
    state_mgr.record_state_change("b", "location", "A", "B", "移动", 2)
    all_changes = state_mgr.get_state_changes()
    assert len(all_changes) == 2
    a_changes = state_mgr.get_state_changes("a")
    assert len(a_changes) == 1


# ---------------------------------------------------------------------------
# 8. Relationships
# ---------------------------------------------------------------------------

def test_add_and_get_relationship(state_mgr):
    state_mgr.add_relationship("a", "b", "师徒", "A是B的师父", chapter=1)
    rels = state_mgr.get_relationships()
    assert len(rels) == 1
    assert rels[0]["from_entity"] == "a"
    assert rels[0]["type"] == "师徒"


def test_get_relationships_by_entity(state_mgr):
    state_mgr.add_relationship("a", "b", "师徒", "desc", chapter=1)
    state_mgr.add_relationship("c", "d", "友人", "desc", chapter=2)
    assert len(state_mgr.get_relationships("a")) == 1
    assert len(state_mgr.get_relationships("d")) == 1
    assert len(state_mgr.get_relationships("z")) == 0


# ---------------------------------------------------------------------------
# 9. save_state (flush to disk)
# ---------------------------------------------------------------------------

def test_save_state_writes_progress(state_mgr):
    state_mgr.update_progress(chapter=10, words=3000)
    state_mgr.save_state()
    disk = json.loads(state_mgr.config.state_file.read_text(encoding="utf-8"))
    assert disk["progress"]["current_chapter"] == 10
    assert disk["progress"]["total_words"] == 3000


def test_save_state_clears_pending(state_mgr):
    state_mgr.update_progress(chapter=1, words=100)
    state_mgr.save_state()
    assert state_mgr._pending_progress_chapter is None
    assert state_mgr._pending_progress_words_delta == 0


def test_save_state_no_pending_does_not_write(config):
    """If there are no pending changes, save_state should not create a file."""
    config.state_file.unlink(missing_ok=True)
    mgr = StateManager(config, enable_sqlite_sync=False)
    mgr.save_state()
    # state.json should not have been created since there were no pending changes
    assert not config.state_file.exists()


def test_save_state_merge_concurrent_progress(config):
    """save_state re-reads disk state and merges, keeping max chapter."""
    # Write initial disk state with chapter=8
    initial = {"progress": {"current_chapter": 8, "total_words": 5000}}
    config.state_file.write_text(json.dumps(initial), encoding="utf-8")

    mgr = StateManager(config, enable_sqlite_sync=False)
    # Simulate another process advancing chapter to 12 on disk
    updated = {"progress": {"current_chapter": 12, "total_words": 8000}}
    config.state_file.write_text(json.dumps(updated), encoding="utf-8")

    # Our manager stages chapter=10 and 1000 words delta
    mgr.update_progress(chapter=10, words=1000)
    mgr.save_state()

    disk = json.loads(config.state_file.read_text(encoding="utf-8"))
    # Should keep max(12, 10) = 12
    assert disk["progress"]["current_chapter"] == 12
    # Should add delta: 8000 + 1000 = 9000
    assert disk["progress"]["total_words"] == 9000


# ---------------------------------------------------------------------------
# 10. export_for_context
# ---------------------------------------------------------------------------

def test_export_for_context_basic(state_mgr):
    state_mgr.add_entity(EntityState(id="hero", name="英雄", type="角色", tier="核心"))
    state_mgr.update_progress(chapter=3, words=5000)
    ctx = state_mgr.export_for_context()
    assert "progress" in ctx
    assert "entities" in ctx
    assert "hero" in ctx["entities"]
    assert ctx["entities"]["hero"]["name"] == "英雄"
    assert "disambiguation" in ctx


# ---------------------------------------------------------------------------
# 11. File locking behaviour
# ---------------------------------------------------------------------------

def test_save_state_uses_file_lock(config, tmp_path):
    """Verify that save_state acquires a file lock."""
    import filelock

    mgr = StateManager(config, enable_sqlite_sync=False)
    mgr.update_progress(chapter=1, words=100)

    lock_path = config.state_file.with_suffix(config.state_file.suffix + ".lock")

    # Hold the lock externally -- save_state should time out
    external_lock = filelock.FileLock(str(lock_path), timeout=0)
    with external_lock:
        with pytest.raises(RuntimeError, match="文件锁"):
            mgr.save_state()


# ---------------------------------------------------------------------------
# 12. Disambiguation pending/warnings via save_state
# ---------------------------------------------------------------------------

def test_save_state_persists_disambiguation(state_mgr):
    state_mgr._pending_disambiguation_warnings.append({
        "chapter": 1,
        "mention": "某人",
        "chosen_id": "char_1",
        "confidence": 0.7,
    })
    state_mgr.save_state()
    disk = json.loads(state_mgr.config.state_file.read_text(encoding="utf-8"))
    assert len(disk["disambiguation_warnings"]) == 1
    assert disk["disambiguation_warnings"][0]["mention"] == "某人"


# ---------------------------------------------------------------------------
# 13. Invalid entity type defaults to 角色
# ---------------------------------------------------------------------------

def test_add_entity_invalid_type_defaults_to_character(state_mgr):
    entity = EntityState(id="x", name="X", type="未知类型")
    state_mgr.add_entity(entity)
    assert "x" in state_mgr._state["entities_v3"]["角色"]


# ---------------------------------------------------------------------------
# 14. chapter_meta via save_state
# ---------------------------------------------------------------------------

def test_save_state_persists_chapter_meta(state_mgr):
    state_mgr._pending_chapter_meta["5"] = {"summary": "第五章摘要", "words": 2000}
    # Need at least one pending item recognised as truthy for has_pending
    state_mgr.save_state()
    disk = json.loads(state_mgr.config.state_file.read_text(encoding="utf-8"))
    assert "5" in disk.get("chapter_meta", {})
    assert disk["chapter_meta"]["5"]["summary"] == "第五章摘要"


# ---------------------------------------------------------------------------
# 15. latest_warnings via save_state
# ---------------------------------------------------------------------------

def test_save_state_persists_latest_warnings(state_mgr):
    state_mgr._pending_latest_warnings.append("warning-1")
    state_mgr._pending_latest_warnings.append("warning-2")
    state_mgr.save_state()
    disk = json.loads(state_mgr.config.state_file.read_text(encoding="utf-8"))
    assert disk["latest_warnings"] == ["warning-1", "warning-2"]
