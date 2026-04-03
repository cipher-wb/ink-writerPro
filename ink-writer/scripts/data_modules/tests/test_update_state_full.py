#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Expanded tests for update_state.py — covers all CLI subcommands."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _inject_path():
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_inject_path()
import update_state as us_mod


def _make_state():
    """Minimal valid state.json dict."""
    return {
        "project_info": {"title": "测试小说"},
        "progress": {"current_chapter": 10, "total_words": 30000},
        "protagonist_state": {
            "power": {"realm": "炼气", "layer": 1, "bottleneck": None},
            "location": {"current": "村口", "last_chapter": 1},
        },
        "relationships": {},
        "world_settings": {},
        "plot_threads": {"foreshadowing": []},
        "review_checkpoints": [],
    }


@pytest.fixture
def project(tmp_path):
    ink = tmp_path / ".ink"
    ink.mkdir()
    state = _make_state()
    (ink / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _run_cli(project, *extra_args):
    """Run update_state.main() with given args, bypassing backup."""
    with patch.object(us_mod.StateUpdater, "backup", return_value=True):
        sys.argv = ["update_state", "--project-root", str(project)] + list(extra_args)
        us_mod.main()
    return json.loads((project / ".ink" / "state.json").read_text(encoding="utf-8"))


# ===========================================================================
# StateUpdater unit tests
# ===========================================================================

class TestStateUpdater:
    def test_load_valid(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        assert updater.load() is True

    def test_load_missing_file(self, tmp_path):
        updater = us_mod.StateUpdater(str(tmp_path / "missing.json"))
        assert updater.load() is False

    def test_load_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        updater = us_mod.StateUpdater(str(bad))
        assert updater.load() is False

    def test_load_missing_required_key(self, tmp_path):
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"project_info": {}}', encoding="utf-8")
        updater = us_mod.StateUpdater(str(incomplete))
        assert updater.load() is False

    def test_validate_schema_flat_power(self, tmp_path):
        state = _make_state()
        state["protagonist_state"] = {
            "realm": "金丹",
            "layer": 3,
            "bottleneck": "雷劫",
            "location": "宗门",
        }
        f = tmp_path / "state.json"
        f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        updater = us_mod.StateUpdater(str(f))
        assert updater.load() is True

    def test_dry_run_does_not_write(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"), dry_run=True)
        updater.load()
        updater.update_progress(99, 999999)
        assert updater.save() is True
        reloaded = json.loads((project / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert reloaded["progress"]["current_chapter"] == 10  # unchanged

    def test_update_protagonist_power_nested(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_protagonist_power("金丹", 3, "雷劫")
        ps = updater.state["protagonist_state"]["power"]
        assert ps["realm"] == "金丹"
        assert ps["layer"] == 3
        assert ps["bottleneck"] == "雷劫"

    def test_update_protagonist_power_flat(self, tmp_path):
        state = _make_state()
        state["protagonist_state"] = {"realm": "炼气", "layer": 1, "bottleneck": None, "location": "村口"}
        f = tmp_path / "state.json"
        f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        updater = us_mod.StateUpdater(str(f))
        updater.load()
        updater.update_protagonist_power("元婴", 1, "null")
        assert updater.state["protagonist_state"]["realm"] == "元婴"
        assert updater.state["protagonist_state"]["bottleneck"] is None

    def test_update_protagonist_location_nested(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_protagonist_location("天剑宗", 50)
        loc = updater.state["protagonist_state"]["location"]
        assert loc["current"] == "天剑宗"
        assert loc["last_chapter"] == 50

    def test_update_golden_finger(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_golden_finger("吞天诀", 5, 3)
        gf = updater.state["protagonist_state"]["golden_finger"]
        assert gf["name"] == "吞天诀"
        assert gf["level"] == 5
        assert gf["cooldown"] == 3

    def test_update_relationship(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_relationship("李雪", "affection", 95)
        assert updater.state["relationships"]["李雪"]["affection"] == 95

    def test_add_foreshadowing(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.add_foreshadowing("神秘玉佩", "未回收")
        items = updater.state["plot_threads"]["foreshadowing"]
        assert len(items) == 1
        assert items[0]["content"] == "神秘玉佩"
        assert items[0]["status"] == "未回收"
        assert items[0]["planted_chapter"] == 10

    def test_add_foreshadowing_duplicate(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.add_foreshadowing("神秘玉佩", "未回收")
        updater.add_foreshadowing("神秘玉佩", "未回收")
        assert len(updater.state["plot_threads"]["foreshadowing"]) == 1

    def test_resolve_foreshadowing(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.add_foreshadowing("天雷果", "未回收")
        updater.resolve_foreshadowing("天雷果", 45)
        item = updater.state["plot_threads"]["foreshadowing"][0]
        assert item["status"] == "已回收"
        assert item["resolved_chapter"] == 45

    def test_resolve_foreshadowing_not_found(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.resolve_foreshadowing("不存在的伏笔", 99)  # should not raise

    def test_update_progress(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_progress(50, 150000)
        assert updater.state["progress"]["current_chapter"] == 50
        assert updater.state["progress"]["total_words"] == 150000

    def test_mark_volume_planned(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.mark_volume_planned(1, "1-100")
        vols = updater.state["progress"]["volumes_planned"]
        assert len(vols) == 1
        assert vols[0]["volume"] == 1

    def test_mark_volume_planned_update_existing(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.mark_volume_planned(1, "1-100")
        updater.mark_volume_planned(1, "1-120")
        vols = updater.state["progress"]["volumes_planned"]
        assert len(vols) == 1
        assert vols[0]["chapters_range"] == "1-120"

    def test_add_review_checkpoint(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.add_review_checkpoint("1-5", "reports/review_1_5.md")
        cp = updater.state["review_checkpoints"]
        assert len(cp) == 1
        assert cp[0]["chapters"] == "1-5"

    def test_update_strand_tracker_valid(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        assert updater.update_strand_tracker("quest", 10) is True
        assert updater.state["strand_tracker"]["current_dominant"] == "quest"
        assert updater.state["strand_tracker"]["last_quest_chapter"] == 10

    def test_update_strand_tracker_switch(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        updater.update_strand_tracker("quest", 10)
        updater.update_strand_tracker("fire", 11)
        assert updater.state["strand_tracker"]["current_dominant"] == "fire"
        assert updater.state["strand_tracker"]["chapters_since_switch"] == 1

    def test_update_strand_tracker_invalid(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        assert updater.update_strand_tracker("invalid", 1) is False

    def test_strand_tracker_history_limit(self, project):
        updater = us_mod.StateUpdater(str(project / ".ink" / "state.json"))
        updater.load()
        for i in range(60):
            updater.update_strand_tracker("quest", i + 1)
        assert len(updater.state["strand_tracker"]["history"]) == 50


# ===========================================================================
# CLI integration tests
# ===========================================================================

class TestCLI:
    def test_protagonist_power(self, project):
        state = _run_cli(project, "--protagonist-power", "金丹", "3", "雷劫")
        ps = state["protagonist_state"]["power"]
        assert ps["realm"] == "金丹"

    def test_protagonist_location(self, project):
        state = _run_cli(project, "--protagonist-location", "天剑宗", "50")
        loc = state["protagonist_state"]["location"]
        assert loc["current"] == "天剑宗"

    def test_golden_finger(self, project):
        state = _run_cli(project, "--golden-finger", "吞天诀", "5", "3")
        gf = state["protagonist_state"]["golden_finger"]
        assert gf["name"] == "吞天诀"

    def test_relationship(self, project):
        state = _run_cli(project, "--relationship", "李雪", "affection", "95")
        assert state["relationships"]["李雪"]["affection"] == 95

    def test_add_foreshadowing(self, project):
        state = _run_cli(project, "--add-foreshadowing", "神秘信件", "未回收")
        items = state["plot_threads"]["foreshadowing"]
        assert any(i["content"] == "神秘信件" for i in items)

    def test_resolve_foreshadowing(self, project):
        _run_cli(project, "--add-foreshadowing", "天雷果", "未回收")
        state = _run_cli(project, "--resolve-foreshadowing", "天雷果", "45")
        item = [i for i in state["plot_threads"]["foreshadowing"] if i["content"] == "天雷果"][0]
        assert item["status"] == "已回收"

    def test_progress(self, project):
        state = _run_cli(project, "--progress", "50", "150000")
        assert state["progress"]["current_chapter"] == 50

    def test_volume_planned(self, project):
        state = _run_cli(project, "--volume-planned", "1", "--chapters-range", "1-100")
        assert state["progress"]["volumes_planned"][0]["volume"] == 1

    def test_strand_dominant(self, project):
        state = _run_cli(project, "--strand-dominant", "fire", "15")
        assert state["strand_tracker"]["current_dominant"] == "fire"

    def test_combined_updates(self, project):
        state = _run_cli(
            project,
            "--protagonist-power", "金丹", "3", "雷劫",
            "--progress", "50", "150000",
            "--relationship", "李雪", "affection", "95",
        )
        assert state["protagonist_state"]["power"]["realm"] == "金丹"
        assert state["progress"]["current_chapter"] == 50
        assert state["relationships"]["李雪"]["affection"] == 95

    def test_no_args_exits(self, project):
        with pytest.raises(SystemExit):
            sys.argv = ["update_state", "--project-root", str(project)]
            us_mod.main()

    def test_dry_run(self, project):
        sys.argv = [
            "update_state", "--project-root", str(project),
            "--dry-run", "--progress", "99", "999999"
        ]
        us_mod.main()
        state = json.loads((project / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert state["progress"]["current_chapter"] == 10  # unchanged

    def test_volume_planned_without_range_exits(self, project):
        with pytest.raises(SystemExit):
            _run_cli(project, "--volume-planned", "1")
