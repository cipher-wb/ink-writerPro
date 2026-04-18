#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for IndexManager core functionality.

Covers: init/schema, integrity check, backup/restore, chapter CRUD,
entity CRUD, alias operations, state changes, relationships, and
schema version tracking.
"""

import sqlite3

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.index.index_manager import (
    IndexManager,
    ChapterMeta,
    SceneMeta,
    EntityMeta,
    StateChangeMeta,
    RelationshipMeta,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def index_mgr(tmp_path):
    """Create an IndexManager backed by a temporary project directory."""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    config = DataModulesConfig.from_project_root(tmp_path)
    return IndexManager(config)


@pytest.fixture
def sample_chapter():
    return ChapterMeta(
        chapter=1,
        title="测试章节",
        location="玄天城",
        word_count=2500,
        characters=["萧尘", "林渊"],
        summary="这是第一章的摘要。",
    )


@pytest.fixture
def sample_entity():
    return EntityMeta(
        id="xiaochen",
        type="角色",
        canonical_name="萧尘",
        tier="核心",
        desc="主角",
        current={"realm": "炼气期", "location": "玄天城"},
        first_appearance=1,
        last_appearance=5,
        is_protagonist=True,
    )


# ---------------------------------------------------------------------------
# 1. Initialisation & Schema
# ---------------------------------------------------------------------------

class TestInitAndSchema:
    def test_init_creates_db_file(self, index_mgr):
        """__init__ should create index.db on disk."""
        assert index_mgr.config.index_db.exists()

    def test_init_creates_tables(self, index_mgr):
        """_init_db should create the expected core tables."""
        conn = sqlite3.connect(str(index_mgr.config.index_db))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r[0] for r in rows}
            expected = {
                "schema_meta",
                "chapters",
                "scenes",
                "appearances",
                "entities",
                "aliases",
                "state_changes",
                "relationships",
            }
            assert expected.issubset(table_names), (
                f"Missing tables: {expected - table_names}"
            )
        finally:
            conn.close()

    def test_schema_version_stored(self, index_mgr):
        """Schema version should be recorded in schema_meta."""
        conn = sqlite3.connect(str(index_mgr.config.index_db))
        try:
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            assert row is not None
            assert int(row[0]) == IndexManager.SCHEMA_VERSION
        finally:
            conn.close()

    def test_table_count_at_least_25(self, index_mgr):
        """The schema should define 25+ tables (as documented)."""
        conn = sqlite3.connect(str(index_mgr.config.index_db))
        try:
            count = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            assert count >= 25, f"Expected >=25 tables, got {count}"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 2. Integrity & Backup
# ---------------------------------------------------------------------------

class TestIntegrityAndBackup:
    def test_check_integrity_ok(self, index_mgr):
        result = index_mgr.check_integrity()
        assert result["ok"] is True
        assert result["table_count"] >= 25
        assert "ok" in result["detail"].lower()

    def test_check_integrity_missing_db(self, tmp_path):
        """check_integrity returns ok=False when db does not exist."""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        config = DataModulesConfig.from_project_root(tmp_path)
        mgr = IndexManager(config)
        # Remove the db file
        mgr.config.index_db.unlink()
        result = mgr.check_integrity()
        assert result["ok"] is False
        assert result["table_count"] == 0

    def test_backup_db_creates_file(self, index_mgr):
        backup_path = index_mgr.backup_db(reason="test")
        assert backup_path is not None
        assert backup_path.exists()
        assert "test" in backup_path.name
        assert backup_path.name.endswith(".bak")

    def test_list_backups(self, index_mgr):
        index_mgr.backup_db(reason="alpha")
        index_mgr.backup_db(reason="beta")
        backups = IndexManager.list_backups(index_mgr.config.ink_dir)
        assert len(backups) >= 2
        names = [b["name"] for b in backups]
        assert any("alpha" in n for n in names)
        assert any("beta" in n for n in names)

    def test_list_backups_empty_dir(self, tmp_path):
        backups = IndexManager.list_backups(tmp_path)
        assert backups == []

    def test_list_backups_missing_dir(self, tmp_path):
        backups = IndexManager.list_backups(tmp_path / "nonexistent")
        assert backups == []


# ---------------------------------------------------------------------------
# 3. Chapter Operations
# ---------------------------------------------------------------------------

class TestChapterOperations:
    def test_add_and_get_chapter(self, index_mgr, sample_chapter):
        index_mgr.add_chapter(sample_chapter)
        ch = index_mgr.get_chapter(1)
        assert ch is not None
        assert ch["chapter"] == 1
        assert ch["title"] == "测试章节"
        assert ch["word_count"] == 2500
        assert ch["characters"] == ["萧尘", "林渊"]

    def test_get_chapter_nonexistent(self, index_mgr):
        assert index_mgr.get_chapter(999) is None

    def test_add_chapter_upsert(self, index_mgr, sample_chapter):
        """add_chapter uses INSERT OR REPLACE, so updating should work."""
        index_mgr.add_chapter(sample_chapter)
        updated = ChapterMeta(
            chapter=1,
            title="更新标题",
            location="新地点",
            word_count=3000,
            characters=["萧尘"],
            summary="更新摘要",
        )
        index_mgr.add_chapter(updated)
        ch = index_mgr.get_chapter(1)
        assert ch["title"] == "更新标题"
        assert ch["word_count"] == 3000

    def test_get_recent_chapters(self, index_mgr):
        for i in range(1, 6):
            index_mgr.add_chapter(
                ChapterMeta(
                    chapter=i,
                    title=f"Ch{i}",
                    location="loc",
                    word_count=1000 * i,
                    characters=[],
                )
            )
        recent = index_mgr.get_recent_chapters(limit=3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["chapter"] == 5
        assert recent[2]["chapter"] == 3

    def test_add_and_get_scenes(self, index_mgr):
        scenes = [
            SceneMeta(chapter=1, scene_index=0, start_line=1, end_line=50,
                      location="客栈", summary="开场", characters=["萧尘"]),
            SceneMeta(chapter=1, scene_index=1, start_line=51, end_line=100,
                      location="街道", summary="追逐", characters=["萧尘", "林渊"]),
        ]
        index_mgr.add_scenes(1, scenes)
        result = index_mgr.get_scenes(1)
        assert len(result) == 2
        assert result[0]["location"] == "客栈"
        assert result[1]["characters"] == ["萧尘", "林渊"]


# ---------------------------------------------------------------------------
# 4. Entity Operations
# ---------------------------------------------------------------------------

class TestEntityOperations:
    def test_upsert_new_entity(self, index_mgr, sample_entity):
        is_new = index_mgr.upsert_entity(sample_entity)
        assert is_new is True

    def test_upsert_existing_entity(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        updated = EntityMeta(
            id="xiaochen",
            type="角色",
            canonical_name="萧尘",
            tier="核心",
            current={"realm": "斗师", "weapon": "玄铁剑"},
            last_appearance=10,
        )
        is_new = index_mgr.upsert_entity(updated)
        assert is_new is False
        entity = index_mgr.get_entity("xiaochen")
        # current should be merged: old location kept, realm overwritten, weapon added
        assert entity["current_json"]["realm"] == "斗师"
        assert entity["current_json"]["location"] == "玄天城"
        assert entity["current_json"]["weapon"] == "玄铁剑"

    def test_get_entity_nonexistent(self, index_mgr):
        assert index_mgr.get_entity("does_not_exist") is None

    def test_get_entities_by_type(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        loc = EntityMeta(
            id="xuantiancheng",
            type="地点",
            canonical_name="玄天城",
        )
        index_mgr.upsert_entity(loc)
        chars = index_mgr.get_entities_by_type("角色")
        assert len(chars) == 1
        assert chars[0]["id"] == "xiaochen"

    def test_get_protagonist(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        p = index_mgr.get_protagonist()
        assert p is not None
        assert p["id"] == "xiaochen"
        assert p["is_protagonist"] == 1

    def test_update_entity_current(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        ok = index_mgr.update_entity_current("xiaochen", {"realm": "斗宗"})
        assert ok is True
        entity = index_mgr.get_entity("xiaochen")
        assert entity["current_json"]["realm"] == "斗宗"
        # Existing keys preserved
        assert entity["current_json"]["location"] == "玄天城"

    def test_archive_entity(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        ok = index_mgr.archive_entity("xiaochen")
        assert ok is True
        # Archived entities excluded by default in get_entities_by_type
        chars = index_mgr.get_entities_by_type("角色")
        assert len(chars) == 0
        # But still retrievable directly
        e = index_mgr.get_entity("xiaochen")
        assert e["is_archived"] == 1


# ---------------------------------------------------------------------------
# 5. Alias Operations
# ---------------------------------------------------------------------------

class TestAliasOperations:
    def test_register_and_resolve_alias(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        ok = index_mgr.register_alias("小尘子", "xiaochen", "角色")
        assert ok is True
        entities = index_mgr.get_entities_by_alias("小尘子")
        assert len(entities) == 1
        assert entities[0]["id"] == "xiaochen"

    def test_alias_one_to_many(self, index_mgr):
        """One alias can map to multiple entities of different types."""
        index_mgr.upsert_entity(EntityMeta(
            id="tianyunzong_loc", type="地点", canonical_name="天云宗",
        ))
        index_mgr.upsert_entity(EntityMeta(
            id="tianyunzong_faction", type="势力", canonical_name="天云宗",
        ))
        index_mgr.register_alias("天云宗", "tianyunzong_loc", "地点")
        index_mgr.register_alias("天云宗", "tianyunzong_faction", "势力")
        entities = index_mgr.get_entities_by_alias("天云宗")
        assert len(entities) == 2
        ids = {e["id"] for e in entities}
        assert ids == {"tianyunzong_loc", "tianyunzong_faction"}

    def test_get_entity_aliases(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        index_mgr.register_alias("小尘子", "xiaochen", "角色")
        index_mgr.register_alias("尘哥", "xiaochen", "角色")
        aliases = index_mgr.get_entity_aliases("xiaochen")
        assert set(aliases) == {"小尘子", "尘哥"}

    def test_remove_alias(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        index_mgr.register_alias("小尘子", "xiaochen", "角色")
        ok = index_mgr.remove_alias("小尘子", "xiaochen")
        assert ok is True
        assert index_mgr.get_entity_aliases("xiaochen") == []


# ---------------------------------------------------------------------------
# 6. State Changes
# ---------------------------------------------------------------------------

class TestStateChanges:
    def test_record_and_query_state_change(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        change = StateChangeMeta(
            entity_id="xiaochen",
            field="realm",
            old_value="炼气期",
            new_value="筑基期",
            reason="突破",
            chapter=3,
        )
        rid = index_mgr.record_state_change(change)
        assert rid > 0
        changes = index_mgr.get_entity_state_changes("xiaochen")
        assert len(changes) == 1
        assert changes[0]["new_value"] == "筑基期"

    def test_get_chapter_state_changes(self, index_mgr, sample_entity):
        index_mgr.upsert_entity(sample_entity)
        for i, (old, new) in enumerate([("炼气", "筑基"), ("筑基", "金丹")]):
            index_mgr.record_state_change(StateChangeMeta(
                entity_id="xiaochen",
                field="realm",
                old_value=old,
                new_value=new,
                reason="突破",
                chapter=i + 1,
            ))
        ch1 = index_mgr.get_chapter_state_changes(1)
        assert len(ch1) == 1
        assert ch1[0]["new_value"] == "筑基"


# ---------------------------------------------------------------------------
# 7. Relationship Operations
# ---------------------------------------------------------------------------

class TestRelationships:
    def test_upsert_new_relationship(self, index_mgr):
        # upsert_relationship auto-creates stub entities if missing
        rel = RelationshipMeta(
            from_entity="xiaochen",
            to_entity="linyuan",
            type="师徒",
            description="萧尘拜林渊为师",
            chapter=1,
        )
        is_new = index_mgr.upsert_relationship(rel)
        assert is_new is True

    def test_upsert_existing_relationship(self, index_mgr):
        rel = RelationshipMeta(
            from_entity="xiaochen",
            to_entity="linyuan",
            type="师徒",
            description="初始",
            chapter=1,
        )
        index_mgr.upsert_relationship(rel)
        updated = RelationshipMeta(
            from_entity="xiaochen",
            to_entity="linyuan",
            type="师徒",
            description="关系加深",
            chapter=5,
        )
        is_new = index_mgr.upsert_relationship(updated)
        assert is_new is False

    def test_get_entity_relationships(self, index_mgr):
        index_mgr.upsert_relationship(RelationshipMeta(
            from_entity="a", to_entity="b", type="友好",
            description="", chapter=1,
        ))
        index_mgr.upsert_relationship(RelationshipMeta(
            from_entity="c", to_entity="a", type="敌对",
            description="", chapter=2,
        ))
        rels = index_mgr.get_entity_relationships("a", direction="both")
        assert len(rels) == 2

    def test_get_relationship_between(self, index_mgr):
        index_mgr.upsert_relationship(RelationshipMeta(
            from_entity="a", to_entity="b", type="友好",
            description="朋友", chapter=1,
        ))
        rels = index_mgr.get_relationship_between("a", "b")
        assert len(rels) == 1
        assert rels[0]["description"] == "朋友"


# ---------------------------------------------------------------------------
# 8. Appearance Records
# ---------------------------------------------------------------------------

class TestAppearances:
    def test_record_and_query_appearance(self, index_mgr):
        index_mgr.record_appearance("xiaochen", chapter=1, mentions=["萧尘", "小尘子"])
        apps = index_mgr.get_entity_appearances("xiaochen")
        assert len(apps) == 1
        assert apps[0]["chapter"] == 1
        assert "萧尘" in apps[0]["mentions"]

    def test_get_chapter_appearances(self, index_mgr):
        index_mgr.record_appearance("xiaochen", chapter=3, mentions=["萧尘"])
        index_mgr.record_appearance("linyuan", chapter=3, mentions=["林渊"])
        apps = index_mgr.get_chapter_appearances(3)
        assert len(apps) == 2

    def test_skip_if_exists(self, index_mgr):
        index_mgr.record_appearance("xiaochen", chapter=1, mentions=["原始"])
        index_mgr.record_appearance(
            "xiaochen", chapter=1, mentions=["覆盖"], skip_if_exists=True
        )
        apps = index_mgr.get_entity_appearances("xiaochen")
        # Should keep original mentions because skip_if_exists=True
        assert apps[0]["mentions"] == ["原始"]


# ---------------------------------------------------------------------------
# 9. Process Chapter Data (integration)
# ---------------------------------------------------------------------------

class TestProcessChapterData:
    def test_process_chapter_data(self, index_mgr):
        stats = index_mgr.process_chapter_data(
            chapter=1,
            title="第一章",
            location="起点",
            word_count=2000,
            entities=[
                {"id": "xiaochen", "type": "角色", "mentions": ["萧尘"], "confidence": 1.0},
                {"id": "linyuan", "type": "角色", "mentions": ["林渊"], "confidence": 0.9},
            ],
            scenes=[
                {"index": 0, "start_line": 1, "end_line": 50, "location": "客栈",
                 "summary": "开场", "characters": ["萧尘"]},
            ],
        )
        assert stats["chapters"] == 1
        assert stats["scenes"] == 1
        assert stats["appearances"] == 2
        # Verify chapter was stored
        ch = index_mgr.get_chapter(1)
        assert ch is not None
        assert ch["title"] == "第一章"
