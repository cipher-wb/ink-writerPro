"""US-019 (FIX-18 P5a): character_progressions 表 + API 往返测试。"""
from __future__ import annotations

import pytest


def _make_idx(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return IndexManager(cfg)


def test_get_progressions_empty(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    assert idx.get_progressions_for_character("char_a") == []


def test_save_and_get_roundtrip(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    idx.save_progression_event({
        "character_id": "char_a",
        "chapter_no": 10,
        "dimension": "power_level",
        "from_value": "炼气三层",
        "to_value": "炼气五层",
        "cause": "突破",
    })
    rows = idx.get_progressions_for_character("char_a")
    assert len(rows) == 1
    assert rows[0]["character_id"] == "char_a"
    assert rows[0]["chapter_no"] == 10
    assert rows[0]["dimension"] == "power_level"
    assert rows[0]["from_value"] == "炼气三层"
    assert rows[0]["to_value"] == "炼气五层"
    assert rows[0]["cause"] == "突破"


def test_upsert_on_conflict(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    base = {
        "character_id": "char_a",
        "chapter_no": 5,
        "dimension": "power_level",
        "from_value": "a",
        "to_value": "b",
        "cause": "初始",
    }
    idx.save_progression_event(base)
    updated = {**base, "to_value": "c", "cause": "修正"}
    idx.save_progression_event(updated)

    rows = idx.get_progressions_for_character("char_a")
    assert len(rows) == 1
    assert rows[0]["to_value"] == "c"
    assert rows[0]["cause"] == "修正"


def test_filter_by_character_and_chapter(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    for char_id, ch, dim in [
        ("char_a", 1, "power_level"),
        ("char_a", 5, "power_level"),
        ("char_a", 10, "relationship"),
        ("char_b", 3, "power_level"),
    ]:
        idx.save_progression_event({
            "character_id": char_id,
            "chapter_no": ch,
            "dimension": dim,
            "to_value": "v",
        })

    # 按角色筛选
    a_all = idx.get_progressions_for_character("char_a")
    assert len(a_all) == 3
    assert all(r["character_id"] == "char_a" for r in a_all)

    b_all = idx.get_progressions_for_character("char_b")
    assert len(b_all) == 1

    # 按章节筛选（before_chapter=6 返回 chapter_no<6）
    a_before_6 = idx.get_progressions_for_character("char_a", before_chapter=6)
    assert len(a_before_6) == 2
    assert all(r["chapter_no"] < 6 for r in a_before_6)

    # 升序校验
    chapters = [r["chapter_no"] for r in a_all]
    assert chapters == sorted(chapters)


def test_missing_required_fields_raises(tmp_path, monkeypatch):
    idx = _make_idx(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        idx.save_progression_event({"chapter_no": 1, "dimension": "x"})
    with pytest.raises(ValueError):
        idx.save_progression_event({"character_id": "a", "dimension": "x"})
    with pytest.raises(ValueError):
        idx.save_progression_event({"character_id": "a", "chapter_no": 1})
