#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def test_build_golden_three_plan_from_init_inputs():
    _ensure_scripts_on_path()

    from data_modules.golden_three import build_golden_three_plan

    plan = build_golden_three_plan(
        title="退婚后我靠系统翻盘",
        genre="xuanhuan",
        target_reader="男频爽文读者",
        platform="番茄",
        opening_hook="前300字写出退婚羞辱和系统异动",
        core_selling_points="退婚反杀,系统加点,资源碾压",
    )

    assert plan["enabled"] is True
    assert plan["gate"] == "hard_first_three"
    assert plan["reader_promise"]
    assert plan["chapters"]["1"]["opening_window_chars"] == 300
    assert "退婚" in plan["chapters"]["1"]["opening_trigger"]
    assert plan["chapters"]["2"]["must_deliver"]
    assert plan["chapters"]["3"]["end_hook_requirement"]


def test_anti_ai_lint_blocks_bad_first_chapter_opening():
    _ensure_scripts_on_path()

    from data_modules.anti_ai_lint import anti_ai_lint_text

    text = (
        "清晨的风很轻，阳光慢慢落在山门上。这个世界共有九块大陆，宗门分为上中下三等。"
        "很多年前，他只是个普通少年。人生有时候就是这样，谁也说不清。"
    )
    result = anti_ai_lint_text(text, chapter=1, genre_profile_key="xianxia")

    assert result["passed"] is False
    issue_ids = {item["id"] for item in result["issues"]}
    assert "golden_three_scenic_opening" in issue_ids
    assert "golden_three_world_building_dump" in issue_ids or "golden_three_missing_trigger" in issue_ids


def test_anti_ai_lint_allows_mystery_triggered_opening():
    _ensure_scripts_on_path()

    from data_modules.anti_ai_lint import anti_ai_lint_text

    text = (
        "广播在凌晨三点准时响起：本栋楼住户不得打开西侧走廊的门。"
        "陈默低头看见自己门缝里塞进来一张写着‘你已经违规一次’的纸条，整个人瞬间清醒。"
    )
    result = anti_ai_lint_text(text, chapter=1, genre_profile_key="rules-mystery")

    assert result["passed"] is True
    assert result["metrics"]["golden_three_applied"] is True
    assert result["metrics"]["golden_three_trigger_detected"] is True


def test_init_project_writes_golden_three_files(tmp_path, monkeypatch):
    _ensure_scripts_on_path()

    import init_project as init_project_module

    project_root = tmp_path / "book"
    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)
    monkeypatch.setattr(init_project_module, "write_current_project_pointer", lambda _path: None)

    init_project_module.init_project(
        str(project_root),
        "测试书",
        "xuanhuan",
        core_selling_points="退婚反杀,系统加点",
        target_reader="男频",
        platform="番茄",
        opening_hook="前300字写出退婚羞辱",
    )

    preferences = json.loads((project_root / ".ink" / "preferences.json").read_text(encoding="utf-8"))
    plan = json.loads((project_root / ".ink" / "golden_three_plan.json").read_text(encoding="utf-8"))
    state = json.loads((project_root / ".ink" / "state.json").read_text(encoding="utf-8"))

    assert preferences["opening_strategy"]["golden_three_enabled"] is True
    assert preferences["opening_strategy"]["gate"] == "hard_first_three"
    assert plan["chapters"]["1"]["opening_window_chars"] == 300
    assert state["project_info"]["opening_hook"] == "前300字写出退婚羞辱"
