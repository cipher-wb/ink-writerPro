#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for EntityLinker
"""

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.extract.entity_linker import EntityLinker, DisambiguationResult
from ink_writer.core.index.index_manager import IndexManager, EntityMeta


@pytest.fixture
def linker(tmp_path):
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    config = DataModulesConfig.from_project_root(tmp_path)
    return EntityLinker(config)


@pytest.fixture
def linker_with_entity(tmp_path):
    """Linker with a pre-registered entity in the entities table."""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    config = DataModulesConfig.from_project_root(tmp_path)
    idx = IndexManager(config)
    idx.upsert_entity(
        EntityMeta(
            id="char_liubei",
            type="角色",
            canonical_name="刘备",
            current={},
            first_appearance=1,
            last_appearance=5,
        )
    )
    idx.upsert_entity(
        EntityMeta(
            id="loc_chengdu",
            type="地点",
            canonical_name="成都",
            current={},
            first_appearance=1,
            last_appearance=3,
        )
    )
    return EntityLinker(config), idx


# ==================== register_alias ====================

def test_register_alias_returns_true(linker_with_entity):
    linker, idx = linker_with_entity
    result = linker.register_alias("char_liubei", "玄德", "角色")
    assert result is True


def test_register_alias_empty_alias_returns_false(linker):
    assert linker.register_alias("char_liubei", "", "角色") is False


def test_register_alias_empty_entity_id_returns_false(linker):
    assert linker.register_alias("", "玄德", "角色") is False


def test_register_alias_duplicate_returns_false(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "玄德", "角色")
    # Second registration of the same alias+entity+type should return False
    result = linker.register_alias("char_liubei", "玄德", "角色")
    assert result is False


# ==================== lookup_alias ====================

def test_lookup_alias_found(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "玄德", "角色")
    result = linker.lookup_alias("玄德")
    assert result == "char_liubei"


def test_lookup_alias_not_found(linker):
    result = linker.lookup_alias("不存在的名字")
    assert result is None


def test_lookup_alias_filter_by_type(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "刘备", "角色")
    linker.register_alias("loc_chengdu", "刘备", "地点")  # same alias, different type
    result = linker.lookup_alias("刘备", entity_type="地点")
    assert result == "loc_chengdu"


def test_lookup_alias_filter_by_type_no_match(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "玄德", "角色")
    result = linker.lookup_alias("玄德", entity_type="地点")
    assert result is None


# ==================== lookup_alias_all ====================

def test_lookup_alias_all_multiple(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "主公", "角色")
    linker.register_alias("loc_chengdu", "主公", "地点")
    results = linker.lookup_alias_all("主公")
    assert len(results) == 2
    ids = {r["id"] for r in results}
    assert "char_liubei" in ids
    assert "loc_chengdu" in ids


def test_lookup_alias_all_empty(linker):
    results = linker.lookup_alias_all("不存在")
    assert results == []


# ==================== get_all_aliases ====================

def test_get_all_aliases(linker_with_entity):
    linker, idx = linker_with_entity
    linker.register_alias("char_liubei", "玄德", "角色")
    linker.register_alias("char_liubei", "刘皇叔", "角色")
    aliases = linker.get_all_aliases("char_liubei")
    assert set(aliases) == {"玄德", "刘皇叔"}


def test_get_all_aliases_none_registered(linker):
    aliases = linker.get_all_aliases("nonexistent")
    assert aliases == []


# ==================== evaluate_confidence ====================

def test_evaluate_confidence_high(linker):
    action, adopt, warning = linker.evaluate_confidence(0.95)
    assert action == "auto"
    assert adopt is True
    assert warning is None


def test_evaluate_confidence_at_high_boundary(linker):
    # Default extraction_confidence_high is 0.8
    action, adopt, warning = linker.evaluate_confidence(0.8)
    assert action == "auto"
    assert adopt is True
    assert warning is None


def test_evaluate_confidence_medium(linker):
    action, adopt, warning = linker.evaluate_confidence(0.6)
    assert action == "warn"
    assert adopt is True
    assert warning is not None
    assert "0.60" in warning


def test_evaluate_confidence_at_medium_boundary(linker):
    # Default extraction_confidence_medium is 0.5
    action, adopt, warning = linker.evaluate_confidence(0.5)
    assert action == "warn"
    assert adopt is True


def test_evaluate_confidence_low(linker):
    action, adopt, warning = linker.evaluate_confidence(0.3)
    assert action == "manual"
    assert adopt is False
    assert warning is not None
    assert "0.30" in warning


def test_evaluate_confidence_zero(linker):
    action, adopt, warning = linker.evaluate_confidence(0.0)
    assert action == "manual"
    assert adopt is False


# ==================== process_uncertain ====================

def test_process_uncertain_high_confidence(linker):
    result = linker.process_uncertain(
        mention="萧炎",
        candidates=["xiaoyan", "xiaoyan2"],
        suggested="xiaoyan",
        confidence=0.9,
    )
    assert isinstance(result, DisambiguationResult)
    assert result.adopted is True
    assert result.entity_id == "xiaoyan"
    assert result.warning is None


def test_process_uncertain_low_confidence(linker):
    result = linker.process_uncertain(
        mention="某人",
        candidates=["a", "b"],
        suggested="a",
        confidence=0.2,
    )
    assert result.adopted is False
    assert result.entity_id is None
    assert result.warning is not None


# ==================== process_extraction_result ====================

def test_process_extraction_result_mixed(linker):
    results, warnings = linker.process_extraction_result([
        {
            "mention": "高手",
            "candidates": ["master1"],
            "suggested": "master1",
            "confidence": 0.9,
        },
        {
            "mention": "路人",
            "candidates": ["npc1"],
            "suggested": "npc1",
            "confidence": 0.3,
        },
    ])
    assert len(results) == 2
    # High confidence has no warning; low confidence does
    assert results[0].warning is None
    assert results[1].warning is not None
    # warnings list includes only items with warnings
    assert len(warnings) >= 1


def test_process_extraction_result_empty(linker):
    results, warnings = linker.process_extraction_result([])
    assert results == []
    assert warnings == []


# ==================== register_new_entities ====================

def test_register_new_entities(linker_with_entity):
    linker, idx = linker_with_entity
    registered = linker.register_new_entities([
        {
            "suggested_id": "char_liubei",
            "type": "角色",
            "name": "刘备",
            "mentions": ["玄德", "刘皇叔"],
        },
    ])
    assert "char_liubei" in registered
    aliases = linker.get_all_aliases("char_liubei")
    assert "刘备" in aliases
    assert "玄德" in aliases
    assert "刘皇叔" in aliases


def test_register_new_entities_skips_new_id(linker):
    registered = linker.register_new_entities([
        {"id": "NEW", "type": "角色", "name": "无名"},
    ])
    assert registered == []


def test_register_new_entities_skips_empty_id(linker):
    registered = linker.register_new_entities([
        {"type": "角色", "name": "无名"},
    ])
    assert registered == []
