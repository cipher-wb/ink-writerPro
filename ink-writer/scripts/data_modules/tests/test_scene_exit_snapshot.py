#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for scene_exit_snapshot in chapter_memory_cards:
write, read back, overwrite on upsert.
"""

import json
import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.index_types import ChapterMemoryCardMeta


@pytest.fixture
def index_mgr(tmp_path):
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    config = DataModulesConfig.from_project_root(tmp_path)
    return IndexManager(config)


@pytest.fixture
def sample_snapshot():
    return [
        {
            "entity_id": "yueyue",
            "location_at_exit": "小区花园入口",
            "emotional_state": "开心但恋恋不舍",
            "relationship_to_protagonist": "初识",
            "contact_established": False,
            "last_action": "被妈妈牵着手走远",
            "open_threads": ["悦悦说过'哥哥明天还来吗'"],
        },
        {
            "entity_id": "yueyue_mama",
            "location_at_exit": "小区花园入口",
            "emotional_state": "中性，略带警惕",
            "relationship_to_protagonist": "陌生",
            "contact_established": False,
            "last_action": "牵着悦悦离开，未回头",
            "open_threads": [],
        },
    ]


class TestSceneExitSnapshotWrite:
    def test_save_with_snapshot(self, index_mgr, sample_snapshot):
        """scene_exit_snapshot 随 chapter_memory_card 一起写入并可读回。"""
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=3,
                summary="悦悦与主角初次相遇",
                goal="建立悦悦角色",
                scene_exit_snapshot=sample_snapshot,
            )
        )
        card = index_mgr.get_chapter_memory_card(3)
        assert card is not None
        snapshot = card.get("scene_exit_snapshot")
        assert isinstance(snapshot, list)
        assert len(snapshot) == 2
        assert snapshot[0]["entity_id"] == "yueyue"
        assert snapshot[0]["contact_established"] is False
        assert snapshot[1]["open_threads"] == []

    def test_save_without_snapshot(self, index_mgr):
        """不传 scene_exit_snapshot 时，字段为 None。"""
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=5,
                summary="普通章节",
            )
        )
        card = index_mgr.get_chapter_memory_card(5)
        assert card is not None
        # scene_exit_snapshot 为空列表时不写入（None）
        snapshot = card.get("scene_exit_snapshot")
        assert snapshot is None

    def test_upsert_overwrites_snapshot(self, index_mgr, sample_snapshot):
        """upsert 时 scene_exit_snapshot 被覆盖更新。"""
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=3,
                summary="初版",
                scene_exit_snapshot=sample_snapshot,
            )
        )
        updated_snapshot = [
            {
                "entity_id": "yueyue",
                "location_at_exit": "主角家门口",
                "emotional_state": "惊喜",
                "relationship_to_protagonist": "熟识",
                "contact_established": True,
                "last_action": "挥手说再见",
                "open_threads": [],
            }
        ]
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=3,
                summary="更新版",
                scene_exit_snapshot=updated_snapshot,
            )
        )
        card = index_mgr.get_chapter_memory_card(3)
        snapshot = card["scene_exit_snapshot"]
        assert len(snapshot) == 1
        assert snapshot[0]["contact_established"] is True
        assert snapshot[0]["location_at_exit"] == "主角家门口"


class TestSceneExitSnapshotRead:
    def test_get_recent_includes_snapshot(self, index_mgr, sample_snapshot):
        """get_recent_chapter_memory_cards 也返回 scene_exit_snapshot。"""
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=1,
                summary="第一章",
                scene_exit_snapshot=sample_snapshot,
            )
        )
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=2,
                summary="第二章",
            )
        )
        cards = index_mgr.get_recent_chapter_memory_cards(limit=5)
        assert len(cards) == 2
        # ch1 has snapshot, ch2 doesn't
        ch1 = next(c for c in cards if c["chapter"] == 1)
        ch2 = next(c for c in cards if c["chapter"] == 2)
        assert isinstance(ch1["scene_exit_snapshot"], list)
        assert len(ch1["scene_exit_snapshot"]) == 2
        assert ch2.get("scene_exit_snapshot") is None

    def test_get_previous_includes_snapshot(self, index_mgr, sample_snapshot):
        """get_previous_chapter_memory_card 返回上一章的 scene_exit_snapshot。"""
        index_mgr.save_chapter_memory_card(
            ChapterMemoryCardMeta(
                chapter=3,
                summary="第三章",
                scene_exit_snapshot=sample_snapshot,
            )
        )
        prev = index_mgr.get_previous_chapter_memory_card(4)
        assert prev is not None
        assert prev["chapter"] == 3
        assert len(prev["scene_exit_snapshot"]) == 2
        assert prev["scene_exit_snapshot"][0]["entity_id"] == "yueyue"
