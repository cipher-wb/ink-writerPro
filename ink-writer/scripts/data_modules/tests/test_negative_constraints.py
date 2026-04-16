#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for negative_constraints table lifecycle:
write, query active, resolve.
"""

import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager


@pytest.fixture
def index_mgr(tmp_path):
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    config = DataModulesConfig.from_project_root(tmp_path)
    return IndexManager(config)


@pytest.fixture
def sample_constraints():
    return [
        {
            "id": "NC-ch0003-001",
            "type": "no_contact_exchange",
            "entities": ["悦悦妈妈", "主角"],
            "description": "悦悦妈妈未与主角交换联系方式",
            "valid_until": None,
            "override_condition": "需要完整的重新相遇+主动交换场景",
        },
        {
            "id": "NC-ch0003-002",
            "type": "no_information_gained",
            "entities": ["主角"],
            "description": "主角未得知悦悦的真实姓名",
            "valid_until": 10,
            "override_condition": "",
        },
        {
            "id": "NC-ch0003-003",
            "type": "no_critical_action",
            "entities": ["悦悦"],
            "description": "悦悦未展现任何超自然能力",
        },
    ]


class TestSaveNegativeConstraints:
    def test_save_returns_count(self, index_mgr, sample_constraints):
        count = index_mgr.save_negative_constraints(3, sample_constraints)
        assert count == 3

    def test_save_empty_list(self, index_mgr):
        count = index_mgr.save_negative_constraints(1, [])
        assert count == 0

    def test_save_upsert_on_duplicate_id(self, index_mgr):
        constraints = [
            {"id": "NC-ch0001-001", "type": "no_contact_exchange", "description": "v1"},
        ]
        index_mgr.save_negative_constraints(1, constraints)
        constraints[0]["description"] = "v2"
        count = index_mgr.save_negative_constraints(1, constraints)
        assert count == 1
        active = index_mgr.get_active_constraints(1)
        assert len(active) == 1
        assert active[0]["description"] == "v2"


class TestGetActiveConstraints:
    def test_returns_all_permanent(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        active = index_mgr.get_active_constraints(5)
        # NC-ch0003-002 has valid_until=10, still active at ch5
        assert len(active) == 3

    def test_filters_expired(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        active = index_mgr.get_active_constraints(11)
        # NC-ch0003-002 expired (valid_until=10, current=11)
        ids = [c["id"] for c in active]
        assert "NC-ch0003-002" not in ids
        assert len(active) == 2

    def test_excludes_resolved(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        index_mgr.resolve_constraint("NC-ch0003-001", 5, "完整重逢场景已写")
        active = index_mgr.get_active_constraints(5)
        ids = [c["id"] for c in active]
        assert "NC-ch0003-001" not in ids

    def test_entities_deserialized(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        active = index_mgr.get_active_constraints(3)
        first = next(c for c in active if c["id"] == "NC-ch0003-001")
        assert isinstance(first["entities"], list)
        assert "悦悦妈妈" in first["entities"]


class TestResolveConstraint:
    def test_resolve_success(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        result = index_mgr.resolve_constraint("NC-ch0003-001", 7, "正文中写了完整建立场景")
        assert result is True

    def test_resolve_nonexistent(self, index_mgr):
        result = index_mgr.resolve_constraint("NC-nonexist", 5, "test")
        assert result is False

    def test_resolve_idempotent(self, index_mgr, sample_constraints):
        index_mgr.save_negative_constraints(3, sample_constraints)
        index_mgr.resolve_constraint("NC-ch0003-001", 7, "first resolve")
        result = index_mgr.resolve_constraint("NC-ch0003-001", 8, "second resolve")
        assert result is False  # already resolved, no row updated


class TestSchemaVersion:
    def test_schema_version_is_2(self, index_mgr):
        assert IndexManager.SCHEMA_VERSION == 2
