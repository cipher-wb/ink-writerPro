#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_schema unit tests

Covers: all Pydantic sub-models, StateModel top-level, defaults,
        validation, extra fields, load_state, save_state round-trip.
"""

import json

import pytest

from state_schema import (
    ChapterMeta,
    EndingMeta,
    GoldenFingerInfo,
    GoldenFingerState,
    HeroineCharacterInfo,
    HookMeta,
    LocationState,
    PatternMeta,
    PlotThreads,
    PowerState,
    ProgressState,
    ProjectInfo,
    ProtagonistState,
    StateModel,
    StrandTracker,
    WorldBuildingInfo,
    WorldSettings,
    load_state,
    save_state,
)


# ---------------------------------------------------------------------------
# PowerState
# ---------------------------------------------------------------------------


class TestPowerState:
    def test_defaults(self):
        ps = PowerState()
        assert ps.realm == ""
        assert ps.layer == 1
        assert ps.bottleneck == ""

    def test_custom_values(self):
        ps = PowerState(realm="金丹", layer=3, bottleneck="雷劫")
        assert ps.realm == "金丹"
        assert ps.layer == 3
        assert ps.bottleneck == "雷劫"

    def test_extra_fields_allowed(self):
        ps = PowerState(realm="筑基", extra_field="hello")
        assert ps.extra_field == "hello"

    def test_invalid_layer_type(self):
        # pydantic v2 coerces strings to int if possible
        ps = PowerState(layer="5")
        assert ps.layer == 5

    def test_model_validate(self):
        ps = PowerState.model_validate({"realm": "化神", "layer": 7})
        assert ps.realm == "化神"
        assert ps.layer == 7


# ---------------------------------------------------------------------------
# LocationState
# ---------------------------------------------------------------------------


class TestLocationState:
    def test_defaults(self):
        ls = LocationState()
        assert ls.current == ""
        assert ls.last_chapter == 0

    def test_custom(self):
        ls = LocationState(current="青云山", last_chapter=42)
        assert ls.current == "青云山"
        assert ls.last_chapter == 42

    def test_extra(self):
        ls = LocationState(current="x", region="east")
        assert ls.region == "east"


# ---------------------------------------------------------------------------
# GoldenFingerState
# ---------------------------------------------------------------------------


class TestGoldenFingerState:
    def test_defaults(self):
        gf = GoldenFingerState()
        assert gf.name == ""
        assert gf.level == 1
        assert gf.cooldown == 0
        assert gf.skills == []

    def test_skills_list(self):
        gf = GoldenFingerState(skills=["火球术", "冰封"])
        assert len(gf.skills) == 2
        assert "火球术" in gf.skills

    def test_extra(self):
        gf = GoldenFingerState(name="系统", bonus=True)
        assert gf.bonus is True


# ---------------------------------------------------------------------------
# ProtagonistState
# ---------------------------------------------------------------------------


class TestProtagonistState:
    def test_defaults(self):
        ps = ProtagonistState()
        assert ps.name == ""
        assert isinstance(ps.power, PowerState)
        assert isinstance(ps.location, LocationState)
        assert isinstance(ps.golden_finger, GoldenFingerState)
        assert ps.attributes == {}

    def test_nested_construction(self):
        ps = ProtagonistState(
            name="萧尘",
            power={"realm": "筑基", "layer": 2},
            location={"current": "天山"},
            golden_finger={"name": "重定义", "skills": ["改写"]},
            attributes={"hp": 100},
        )
        assert ps.name == "萧尘"
        assert ps.power.realm == "筑基"
        assert ps.location.current == "天山"
        assert ps.golden_finger.skills == ["改写"]
        assert ps.attributes["hp"] == 100

    def test_extra(self):
        ps = ProtagonistState(name="a", mood="angry")
        assert ps.mood == "angry"


# ---------------------------------------------------------------------------
# ProgressState
# ---------------------------------------------------------------------------


class TestProgressState:
    def test_defaults(self):
        ps = ProgressState()
        assert ps.current_chapter == 0
        assert ps.total_words == 0
        assert ps.current_volume == 1
        assert ps.volumes_completed == []
        assert ps.volumes_planned == []
        # last_updated should be a date-like string
        assert len(ps.last_updated) > 0

    def test_custom(self):
        ps = ProgressState(current_chapter=10, total_words=50000, current_volume=2)
        assert ps.current_chapter == 10
        assert ps.total_words == 50000

    def test_extra(self):
        ps = ProgressState(daily_target=3000)
        assert ps.daily_target == 3000


# ---------------------------------------------------------------------------
# WorldSettings
# ---------------------------------------------------------------------------


class TestWorldSettings:
    def test_defaults(self):
        ws = WorldSettings()
        assert ws.power_system == []
        assert ws.factions == []
        assert ws.locations == []

    def test_custom(self):
        ws = WorldSettings(
            power_system=["练气", "筑基"],
            factions=[{"name": "正道"}],
            locations=["青云山"],
        )
        assert len(ws.power_system) == 2
        assert ws.factions[0]["name"] == "正道"


# ---------------------------------------------------------------------------
# PlotThreads
# ---------------------------------------------------------------------------


class TestPlotThreads:
    def test_defaults(self):
        pt = PlotThreads()
        assert pt.active_threads == []
        assert pt.foreshadowing == []

    def test_custom(self):
        pt = PlotThreads(active_threads=["主线"], foreshadowing=["伏笔1"])
        assert len(pt.active_threads) == 1


# ---------------------------------------------------------------------------
# StrandTracker
# ---------------------------------------------------------------------------


class TestStrandTracker:
    def test_defaults(self):
        st = StrandTracker()
        assert st.last_quest_chapter == 0
        assert st.last_fire_chapter == 0
        assert st.last_constellation_chapter == 0
        assert st.current_dominant == "quest"
        assert st.chapters_since_switch == 0
        assert st.history == []

    def test_custom(self):
        st = StrandTracker(
            last_quest_chapter=5,
            last_fire_chapter=3,
            current_dominant="fire",
            chapters_since_switch=2,
            history=[{"ch": 1, "strand": "quest"}],
        )
        assert st.current_dominant == "fire"
        assert len(st.history) == 1

    def test_extra(self):
        st = StrandTracker(notes="test")
        assert st.notes == "test"


# ---------------------------------------------------------------------------
# HookMeta / PatternMeta / EndingMeta / ChapterMeta
# ---------------------------------------------------------------------------


class TestHookMeta:
    def test_defaults(self):
        h = HookMeta()
        assert h.type == ""
        assert h.content == ""
        assert h.strength == ""

    def test_custom(self):
        h = HookMeta(type="suspense", content="谁在门后", strength="strong")
        assert h.type == "suspense"


class TestPatternMeta:
    def test_defaults(self):
        p = PatternMeta()
        assert p.opening == ""
        assert p.hook == ""
        assert p.emotion_rhythm == ""


class TestEndingMeta:
    def test_defaults(self):
        e = EndingMeta()
        assert e.time == ""
        assert e.location == ""
        assert e.emotion == ""


class TestChapterMeta:
    def test_defaults(self):
        cm = ChapterMeta()
        assert cm.version == 1
        assert len(cm.updated_at) > 0
        assert isinstance(cm.hook, HookMeta)
        assert isinstance(cm.pattern, PatternMeta)
        assert isinstance(cm.ending, EndingMeta)

    def test_nested(self):
        cm = ChapterMeta(
            version=2,
            hook={"type": "cliffhanger", "content": "...", "strength": "high"},
            pattern={"opening": "action"},
            ending={"emotion": "tense"},
        )
        assert cm.version == 2
        assert cm.hook.type == "cliffhanger"
        assert cm.pattern.opening == "action"
        assert cm.ending.emotion == "tense"

    def test_extra(self):
        cm = ChapterMeta(custom_note="abc")
        assert cm.custom_note == "abc"


# ---------------------------------------------------------------------------
# ProjectInfo sub-models
# ---------------------------------------------------------------------------


class TestGoldenFingerInfo:
    def test_defaults(self):
        gfi = GoldenFingerInfo()
        assert gfi.name is None
        assert gfi.type is None
        assert gfi.style is None
        assert gfi.visibility is None
        assert gfi.irreversible_cost is None

    def test_custom(self):
        gfi = GoldenFingerInfo(name="系统", type="辅助", style="渐进")
        assert gfi.name == "系统"


class TestHeroineCharacterInfo:
    def test_defaults(self):
        h = HeroineCharacterInfo()
        assert h.config is None
        assert h.names is None
        assert h.role is None

    def test_custom(self):
        h = HeroineCharacterInfo(config="single", names="苏清玄", role="主要")
        assert h.names == "苏清玄"


class TestWorldBuildingInfo:
    def test_defaults(self):
        wb = WorldBuildingInfo()
        assert wb.scale is None
        assert wb.factions is None
        assert wb.power_system_type is None
        assert wb.social_class is None
        assert wb.resource_distribution is None
        assert wb.currency_system is None
        assert wb.currency_exchange is None
        assert wb.sect_hierarchy is None
        assert wb.cultivation_chain is None
        assert wb.cultivation_subtiers is None

    def test_custom(self):
        wb = WorldBuildingInfo(scale="大陆", factions="三大势力")
        assert wb.scale == "大陆"


# ---------------------------------------------------------------------------
# ProjectInfo
# ---------------------------------------------------------------------------


class TestProjectInfo:
    def test_defaults(self):
        pi = ProjectInfo()
        assert pi.title is None
        assert pi.genre is None
        assert pi.target_words is None
        assert pi.themes == []
        assert isinstance(pi.golden_finger, GoldenFingerInfo)
        assert isinstance(pi.heroine, HeroineCharacterInfo)
        assert isinstance(pi.world_building, WorldBuildingInfo)

    def test_full_construction(self):
        pi = ProjectInfo(
            title="测试小说",
            genre="玄幻",
            target_words=2000000,
            target_chapters=1000,
            themes=["成长", "复仇"],
            golden_finger={"name": "系统"},
            heroine={"names": "林小姐"},
            world_building={"scale": "九界"},
        )
        assert pi.title == "测试小说"
        assert pi.target_words == 2000000
        assert len(pi.themes) == 2
        assert pi.golden_finger.name == "系统"
        assert pi.heroine.names == "林小姐"
        assert pi.world_building.scale == "九界"

    def test_legacy_fields(self):
        """Old flat fields should still be accepted."""
        pi = ProjectInfo(
            golden_finger_name="旧系统",
            heroine_config="multi",
            world_scale="小",
            factions="两派",
        )
        assert pi.golden_finger_name == "旧系统"
        assert pi.heroine_config == "multi"
        assert pi.world_scale == "小"

    def test_extra(self):
        pi = ProjectInfo(unknown_field="val")
        assert pi.unknown_field == "val"


# ---------------------------------------------------------------------------
# StateModel (top-level)
# ---------------------------------------------------------------------------


class TestStateModel:
    def test_defaults(self):
        sm = StateModel()
        assert sm.schema_version == 9
        assert isinstance(sm.project_info, ProjectInfo)
        assert isinstance(sm.progress, ProgressState)
        assert isinstance(sm.protagonist_state, ProtagonistState)
        assert sm.relationships == {}
        assert sm.disambiguation_warnings == []
        assert sm.disambiguation_pending == []
        assert isinstance(sm.world_settings, WorldSettings)
        assert isinstance(sm.plot_threads, PlotThreads)
        assert sm.review_checkpoints == []
        assert sm.chapter_meta == {}
        assert isinstance(sm.strand_tracker, StrandTracker)

    def test_model_validate_empty(self):
        sm = StateModel.model_validate({})
        assert sm.schema_version == 9

    def test_model_validate_full(self):
        data = {
            "schema_version": 9,
            "project_info": {"title": "TestBook", "genre": "sci-fi"},
            "progress": {"current_chapter": 5, "total_words": 12000},
            "protagonist_state": {
                "name": "Hero",
                "power": {"realm": "练气", "layer": 3},
            },
            "relationships": {"Hero-Villain": {"type": "enemy"}},
            "disambiguation_warnings": ["warn1"],
            "disambiguation_pending": [{"id": 1}],
            "world_settings": {"power_system": ["qi"]},
            "plot_threads": {"active_threads": ["main"]},
            "review_checkpoints": [{"ch": 1}],
            "chapter_meta": {
                "ch001": {"version": 2, "hook": {"type": "mystery"}}
            },
            "strand_tracker": {"current_dominant": "fire"},
        }
        sm = StateModel.model_validate(data)
        assert sm.schema_version == 9
        assert sm.project_info.title == "TestBook"
        assert sm.progress.current_chapter == 5
        assert sm.protagonist_state.power.realm == "练气"
        assert sm.relationships["Hero-Villain"]["type"] == "enemy"
        assert len(sm.disambiguation_warnings) == 1
        assert sm.chapter_meta["ch001"].hook.type == "mystery"
        assert sm.strand_tracker.current_dominant == "fire"

    def test_extra_top_level_fields(self):
        sm = StateModel.model_validate({"custom_key": [1, 2, 3]})
        assert sm.custom_key == [1, 2, 3]

    def test_model_dump_json(self):
        sm = StateModel(schema_version=6)
        dumped = sm.model_dump_json(indent=2, exclude_none=True)
        parsed = json.loads(dumped)
        assert parsed["schema_version"] == 6
        assert "progress" in parsed

    def test_chapter_meta_dict_of_models(self):
        sm = StateModel(
            chapter_meta={
                "ch001": ChapterMeta(version=1),
                "ch002": ChapterMeta(version=2),
            }
        )
        assert sm.chapter_meta["ch001"].version == 1
        assert sm.chapter_meta["ch002"].version == 2

    def test_chapter_meta_from_raw_dict(self):
        sm = StateModel.model_validate({
            "chapter_meta": {
                "ch001": {"version": 3, "hook": {"type": "action"}},
            }
        })
        assert isinstance(sm.chapter_meta["ch001"], ChapterMeta)
        assert sm.chapter_meta["ch001"].version == 3


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------


class TestLoadState:
    def test_load_missing_file_returns_default(self, tmp_path):
        """When state.json doesn't exist, return a default StateModel."""
        state = load_state(tmp_path)
        assert isinstance(state, StateModel)
        assert state.schema_version == 9

    def test_load_existing_file(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        data = {
            "schema_version": 6,
            "progress": {"current_chapter": 10, "total_words": 20000},
            "protagonist_state": {"name": "测试主角"},
        }
        (ink_dir / "state.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        state = load_state(tmp_path)
        assert state.progress.current_chapter == 10
        assert state.protagonist_state.name == "测试主角"

    def test_load_with_string_path(self, tmp_path):
        """load_state accepts str as well as Path."""
        state = load_state(str(tmp_path))
        assert isinstance(state, StateModel)

    def test_load_file_with_extra_fields(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        data = {"schema_version": 6, "some_future_field": True}
        (ink_dir / "state.json").write_text(json.dumps(data), encoding="utf-8")
        state = load_state(tmp_path)
        assert state.some_future_field is True

    def test_load_minimal_json(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")
        state = load_state(tmp_path)
        assert state.schema_version == 9


class TestSaveState:
    def test_save_creates_ink_dir(self, tmp_path):
        """save_state should create .ink/ if it doesn't exist."""
        state = StateModel(schema_version=6)
        save_state(tmp_path, state)
        assert (tmp_path / ".ink" / "state.json").exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        state = StateModel(
            schema_version=6,
            progress=ProgressState(current_chapter=7, total_words=15000),
            protagonist_state=ProtagonistState(
                name="萧尘",
                power=PowerState(realm="金丹", layer=4),
            ),
            relationships={"A-B": {"type": "ally"}},
            chapter_meta={
                "ch001": ChapterMeta(version=1, hook=HookMeta(type="suspense")),
            },
        )
        save_state(tmp_path, state)
        loaded = load_state(tmp_path)

        assert loaded.schema_version == 6  # roundtrip preserves original version
        assert loaded.progress.current_chapter == 7
        assert loaded.protagonist_state.name == "萧尘"
        assert loaded.protagonist_state.power.realm == "金丹"
        assert loaded.relationships["A-B"]["type"] == "ally"
        assert loaded.chapter_meta["ch001"].hook.type == "suspense"

    def test_save_with_string_path(self, tmp_path):
        state = StateModel()
        save_state(str(tmp_path), state)
        assert (tmp_path / ".ink" / "state.json").exists()

    def test_save_excludes_none(self, tmp_path):
        """exclude_none=True should omit None fields from JSON."""
        state = StateModel(
            project_info=ProjectInfo(title="Test", genre=None)
        )
        save_state(tmp_path, state)
        raw = json.loads(
            (tmp_path / ".ink" / "state.json").read_text(encoding="utf-8")
        )
        pi = raw.get("project_info", {})
        assert "title" in pi
        assert "genre" not in pi

    def test_save_overwrites_existing(self, tmp_path):
        state1 = StateModel(progress=ProgressState(current_chapter=1))
        save_state(tmp_path, state1)
        state2 = StateModel(progress=ProgressState(current_chapter=99))
        save_state(tmp_path, state2)
        loaded = load_state(tmp_path)
        assert loaded.progress.current_chapter == 99

    def test_save_preserves_utf8(self, tmp_path):
        state = StateModel(
            protagonist_state=ProtagonistState(name="萧尘"),
            project_info=ProjectInfo(title="修仙之路"),
        )
        save_state(tmp_path, state)
        raw_text = (tmp_path / ".ink" / "state.json").read_text(encoding="utf-8")
        assert "萧尘" in raw_text
        assert "修仙之路" in raw_text


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    def test_coerce_int_from_string(self):
        ps = ProgressState.model_validate({"current_chapter": "10"})
        assert ps.current_chapter == 10

    def test_invalid_type_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PowerState.model_validate({"layer": "not_a_number"})

    def test_empty_skills_list(self):
        gf = GoldenFingerState(skills=[])
        assert gf.skills == []

    def test_deeply_nested_roundtrip(self, tmp_path):
        """Full model with all nested sub-models survives save/load."""
        state = StateModel(
            schema_version=6,
            project_info=ProjectInfo(
                title="深度测试",
                themes=["a", "b"],
                golden_finger=GoldenFingerInfo(name="gf1"),
                heroine=HeroineCharacterInfo(config="single"),
                world_building=WorldBuildingInfo(scale="九界"),
            ),
            protagonist_state=ProtagonistState(
                name="主角",
                power=PowerState(realm="渡劫", layer=9),
                location=LocationState(current="天宫", last_chapter=100),
                golden_finger=GoldenFingerState(
                    name="天道系统", level=5, skills=["天罚", "轮回"]
                ),
                attributes={"luck": 99},
            ),
            strand_tracker=StrandTracker(
                last_quest_chapter=50,
                current_dominant="constellation",
                history=[{"ch": 1}, {"ch": 2}],
            ),
        )
        save_state(tmp_path, state)
        loaded = load_state(tmp_path)

        assert loaded.project_info.golden_finger.name == "gf1"
        assert loaded.project_info.heroine.config == "single"
        assert loaded.project_info.world_building.scale == "九界"
        assert loaded.protagonist_state.golden_finger.skills == ["天罚", "轮回"]
        assert loaded.protagonist_state.attributes["luck"] == 99
        assert loaded.strand_tracker.current_dominant == "constellation"
        assert len(loaded.strand_tracker.history) == 2
