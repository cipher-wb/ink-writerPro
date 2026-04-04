#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json


def test_extract_state_summary_accepts_dominant_key(tmp_path):

    from extract_chapter_context import extract_state_summary

    state = {
        "progress": {"current_chapter": 12, "total_words": 12345},
        "protagonist_state": {
            "power": {"realm": "筑基", "layer": 2},
            "location": "宗门",
            "golden_finger": {"name": "系统", "level": 1},
        },
        "strand_tracker": {
            "history": [
                {"chapter": 10, "dominant": "quest"},
                {"chapter": 11, "dominant": "fire"},
            ]
        },
    }

    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir(parents=True, exist_ok=True)
    (ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    text = extract_state_summary(tmp_path)
    assert "Ch10:quest" in text
    assert "Ch11:fire" in text


def test_extract_chapter_outline_supports_hyphen_filename(tmp_path):

    from extract_chapter_context import extract_chapter_outline

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷-详细大纲.md").write_text("### 第1章：测试标题\n测试大纲", encoding="utf-8")

    outline = extract_chapter_outline(tmp_path, 1)
    assert "### 第1章：测试标题" in outline
    assert "测试大纲" in outline


def test_extract_chapter_outline_prefers_state_volume_mapping(tmp_path):

    from extract_chapter_context import extract_chapter_outline

    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "progress": {
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-10"},
                {"volume": 2, "chapters_range": "11-20"},
            ]
        }
    }
    (ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第2卷-详细大纲.md").write_text("### 第12章：V2标题\nV2大纲", encoding="utf-8")

    outline = extract_chapter_outline(tmp_path, 12)
    assert "### 第12章：V2标题" in outline
    assert "V2大纲" in outline


def test_extract_chapter_outline_falls_back_when_state_has_no_match(tmp_path):

    from extract_chapter_context import extract_chapter_outline

    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir(parents=True, exist_ok=True)
    state = {"progress": {"volumes_planned": [{"volume": 1, "chapters_range": "1-10"}]}}
    (ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第2卷-详细大纲.md").write_text("### 第60章：V2标题\nV2大纲", encoding="utf-8")

    outline = extract_chapter_outline(tmp_path, 60)
    assert "### 第60章：V2标题" in outline
    assert "V2大纲" in outline


def test_build_chapter_context_payload_includes_contract_sections(tmp_path):

    from extract_chapter_context import build_chapter_context_payload
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager, ChapterReadingPowerMeta, ReviewMetrics

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        "project": {"genre": "xuanhuan"},
        "project_info": {
            "title": "测试书",
            "genre": "xuanhuan",
            "target_reader": "男频",
            "platform": "番茄",
            "core_selling_points": "退婚反杀,系统加点",
        },
        "progress": {"current_chapter": 3, "total_words": 9000},
        "protagonist_state": {
            "power": {"realm": "筑基", "layer": 2},
            "location": "宗门",
            "golden_finger": {"name": "系统", "level": 1},
        },
        "strand_tracker": {"history": [{"chapter": 2, "dominant": "quest"}]},
        "chapter_meta": {},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (cfg.ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    summaries_dir = cfg.ink_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    (summaries_dir / "ch0002.md").write_text("## 剧情摘要\n上一章总结", encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text("### 第3章：测试标题\n测试大纲", encoding="utf-8")

    refs_dir = tmp_path / ".claude" / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "genre-profiles.md").write_text("## xuanhuan\n- 升级线清晰", encoding="utf-8")
    (refs_dir / "reading-power-taxonomy.md").write_text("## xuanhuan\n- 悬念钩优先", encoding="utf-8")
    (cfg.ink_dir / "golden_three_plan.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "chapters": {
                    "3": {
                        "chapter": 3,
                        "golden_three_role": "小闭环",
                        "opening_window_chars": 500,
                        "opening_trigger": "尽快承接前两章压力",
                        "reader_promise": "兑现退婚反杀的第一轮收益",
                        "must_deliver": ["完成首个小闭环", "资源或身份出现显性变化"],
                        "micro_payoffs": ["拿到第一笔收益"],
                        "end_hook_requirement": "章末把读者送入长线主故事",
                        "forbidden_slow_zones": ["世界观讲解"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    idx = IndexManager(cfg)
    idx.save_chapter_reading_power(
        ChapterReadingPowerMeta(chapter=2, hook_type="悬念钩", hook_strength="strong", coolpoint_patterns=["身份掉马"])
    )
    idx.save_review_metrics(
        ReviewMetrics(start_chapter=1, end_chapter=2, overall_score=71, dimension_scores={"plot": 71})
    )

    payload = build_chapter_context_payload(tmp_path, 3)
    assert payload["context_contract_version"] == "v3"
    assert payload.get("context_weight_stage") in {"early", "mid", "late"}
    assert payload["golden_three_contract"]["golden_three_role"] == "小闭环"
    assert "writing_guidance" in payload
    assert isinstance(payload["writing_guidance"].get("guidance_items"), list)
    assert isinstance(payload["writing_guidance"].get("checklist"), list)
    assert isinstance(payload["writing_guidance"].get("checklist_score"), dict)
    assert payload["genre_profile"].get("genre") == "xuanhuan"
    assert "rag_assist" in payload
    assert isinstance(payload["rag_assist"], dict)
    assert payload["rag_assist"].get("invoked") is False


def test_build_chapter_context_payload_uses_memory_card_local_rag_fallback(tmp_path):

    from extract_chapter_context import build_chapter_context_payload
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager, ChapterMemoryCardMeta

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        "project": {"genre": "xuanhuan"},
        "progress": {"current_chapter": 3, "total_words": 9000},
        "protagonist_state": {"name": "萧炎"},
        "chapter_meta": {},
        "plot_threads": {"active_threads": [], "foreshadowing": []},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (cfg.ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text(
        "### 第3章：戒指异动\n本章围绕戒指异动、药老隐瞒和上一章遗留的身份疑问展开，必须接住前夜留下的悬念。",
        encoding="utf-8",
    )

    idx = IndexManager(cfg)
    idx.save_chapter_memory_card(
        ChapterMemoryCardMeta(
            chapter=2,
            summary="萧炎发现戒指发热，药老却选择沉默。",
            next_chapter_bridge="必须接住戒指发热与药老隐瞒",
            involved_entities=["xiaoyan"],
            key_facts=["戒指发热"],
        )
    )

    payload = build_chapter_context_payload(tmp_path, 3)
    assert payload["memory_context"]["previous_chapter_memory_card"]["chapter"] == 2
    assert payload["rag_assist"]["invoked"] is True
    assert payload["rag_assist"]["mode"] == "summary_memory_bm25"
    assert payload["rag_assist"]["hits"]


def test_build_execution_pack_payload_contains_golden_three_prompt_sections(tmp_path):

    from extract_chapter_context import build_chapter_context_payload, build_execution_pack_payload
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import (
        ChapterMemoryCardMeta,
        ChapterReadingPowerMeta,
        IndexManager,
        PlotThreadRegistryMeta,
        ReviewMetrics,
        TimelineAnchorMeta,
    )

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        "project": {"genre": "xianxia"},
        "project_info": {
            "title": "测试书",
            "genre": "xianxia",
            "target_reader": "男频",
            "platform": "番茄",
            "core_selling_points": "退婚反杀,系统加点",
        },
        "progress": {"current_chapter": 2, "total_words": 5200},
        "protagonist_state": {
            "name": "林渡",
            "power": {"realm": "炼气", "layer": 9},
            "location": "外门演武场",
            "golden_finger": {"name": "命格面板", "level": 2},
        },
        "chapter_meta": {},
        "plot_threads": {"foreshadowing": []},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (cfg.ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text(
        "\n".join(
            [
                "### 第2章：灵碑亮起",
                "- 本章目标：接住首章灵碑异动，逼主角在众目睽睽下做出选择",
                "- 冲突：长老压制，主角必须在暴露与隐忍之间取舍",
                "- 代价：一旦暴露，旧敌会提前盯上他",
                "- 本章变化：主角第一次公开拿到灵碑回应",
                "- 章末钩子：章末必须把期待升级为必须看第3章",
            ]
        ),
        encoding="utf-8",
    )

    (cfg.ink_dir / "summaries").mkdir(parents=True, exist_ok=True)
    (cfg.ink_dir / "summaries" / "ch0001.md").write_text("## 剧情摘要\n林渡发现灵碑异动，被外门长老盯上。", encoding="utf-8")
    (cfg.ink_dir / "golden_three_plan.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "chapters": {
                    "2": {
                        "chapter": 2,
                        "golden_three_role": "接住首章钩子并升级代价/规则",
                        "opening_window_chars": 500,
                        "opening_trigger": "前500字回应灵碑异动",
                        "reader_promise": "退婚反杀 + 系统加点",
                        "must_deliver": ["回应首章钩子", "升级代价", "给至少1个微兑现"],
                        "micro_payoffs": ["第一次灵碑回应", "外门弟子态度变化"],
                        "end_hook_requirement": "把期待升级为必须看第3章",
                        "forbidden_slow_zones": ["景物空镜", "世界观讲解"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    idx = IndexManager(cfg)
    idx.save_chapter_memory_card(
        ChapterMemoryCardMeta(
            chapter=1,
            summary="林渡察觉灵碑异动，引来长老关注。",
            next_chapter_bridge="必须接住灵碑异动与长老压制",
            unresolved_questions=["灵碑为什么只回应林渡"],
            key_facts=["灵碑异动", "长老起疑"],
            involved_entities=["lindu", "elder_han"],
        )
    )
    idx.upsert_plot_thread(
        PlotThreadRegistryMeta(
            thread_id="thread_lingbei",
            title="灵碑异动",
            content="灵碑为何只对林渡起反应",
            status="active",
            priority=90,
            planted_chapter=1,
            last_touched_chapter=1,
            target_payoff_chapter=3,
            related_entities=["lindu"],
        )
    )
    idx.save_timeline_anchor(
        TimelineAnchorMeta(
            chapter=1,
            anchor_time="外门大比前夜",
            relative_to_previous="首章起点",
            countdown="大比 D-1",
            to_location="外门演武场",
        )
    )
    idx.save_chapter_reading_power(
        ChapterReadingPowerMeta(
            chapter=1,
            hook_type="悬念钩",
            hook_strength="strong",
            coolpoint_patterns=["身份压制"],
            micropayoffs=["灵碑异动"],
        )
    )
    idx.save_review_metrics(
        ReviewMetrics(
            start_chapter=1,
            end_chapter=1,
            overall_score=82,
            dimension_scores={"plot": 82},
        )
    )

    payload = build_chapter_context_payload(tmp_path, 2)
    pack = build_execution_pack_payload(payload)

    assert pack["mode"] == "golden_three"
    assert "本章核心任务" in pack["taskbook"]
    assert any("回应首章钩子" in row for row in pack["taskbook"]["本章核心任务"])
    assert any("读者承诺" in row for row in pack["taskbook"]["追读力策略"])
    assert pack["context_contract"]["开头类型"]
    assert pack["step_2a_prompt"]["章节节拍"]
    assert pack["step_2a_prompt"]["不可变事实清单"]


def test_build_execution_pack_payload_preserves_chapter_two_continuity(tmp_path):

    from extract_chapter_context import build_chapter_context_payload, build_execution_pack_payload
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import (
        ChapterMemoryCardMeta,
        CandidateFactMeta,
        IndexManager,
        PlotThreadRegistryMeta,
        TimelineAnchorMeta,
    )
    from data_modules.index_manager import StateChangeMeta

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        "project": {"genre": "rules-mystery"},
        "project_info": {"title": "规则门外", "genre": "rules-mystery"},
        "progress": {"current_chapter": 1, "total_words": 2600},
        "protagonist_state": {
            "name": "许沉",
            "power": {"realm": "普通人", "layer": 0},
            "location": "四号楼值班室",
        },
        "chapter_meta": {},
        "plot_threads": {"foreshadowing": []},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (cfg.ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text(
        "\n".join(
            [
                "### 第2章：第二条广播",
                "- 本章目标：回应第1章末尾广播，确认规则真的在生效",
                "- 冲突：值班室必须在停电前完成登记，否则整层被清算",
                "- 代价：许沉一旦违规，身份会被广播标红",
                "- 本章变化：主角第一次主动利用规则漏洞",
            ]
        ),
        encoding="utf-8",
    )

    idx = IndexManager(cfg)
    idx.save_chapter_memory_card(
        ChapterMemoryCardMeta(
            chapter=1,
            summary="许沉在值班室听到第一条广播，楼层规则开始收缩。",
            next_chapter_bridge="必须接住第一条广播与停电倒计时",
            unresolved_questions=["广播来源是什么"],
            involved_entities=["xuchen", "broadcast"],
        )
    )
    idx.upsert_plot_thread(
        PlotThreadRegistryMeta(
            thread_id="thread_broadcast",
            title="广播来源",
            content="广播为何只在四号楼循环",
            status="active",
            priority=95,
            planted_chapter=1,
            last_touched_chapter=1,
            target_payoff_chapter=4,
            related_entities=["broadcast"],
        )
    )
    idx.save_timeline_anchor(
        TimelineAnchorMeta(
            chapter=1,
            anchor_time="停电前 20 分钟",
            relative_to_previous="首章",
            countdown="停电 D-0 00:20",
            to_location="四号楼值班室",
        )
    )
    idx.record_state_change(
        StateChangeMeta(
            entity_id="xuchen",
            field="risk_level",
            old_value="yellow",
            new_value="orange",
            reason="广播点名",
            chapter=1,
        )
    )
    idx.save_candidate_fact(
        CandidateFactMeta(
            chapter=1,
            fact="广播可能认识许沉的工号",
            entity_id="broadcast",
            confidence=0.42,
            evidence="广播里直接读出末尾四位工号",
        )
    )

    payload = build_chapter_context_payload(tmp_path, 2)
    pack = build_execution_pack_payload(payload)

    assert any("上章摘要" in row for row in pack["taskbook"]["接住上章"])
    assert any("停电前 20 分钟" in row for row in pack["taskbook"]["时间约束"])
    assert any("活跃线程" in row for row in pack["taskbook"]["连续性与伏笔"])
    assert any("低置信度候选事实" in row for row in pack["taskbook"]["连续性与伏笔"])
    assert any("时间线" in row for row in pack["step_2a_prompt"]["不可变事实清单"])


def test_execution_pack_json_is_more_compact_than_full_payload():

    from extract_chapter_context import build_execution_pack_payload

    payload = {
        "chapter": 2,
        "outline": "### 第2章：测试标题\n- 本章目标：接住上章钩子\n- 冲突：强敌压制\n- 代价：暴露底牌\n- 本章变化：拿到首次收益",
        "previous_summaries": [
            "### 第1章摘要\n" + "上一章总结。" * 80,
            "### 第0章摘要\n" + "背景补充。" * 60,
        ],
        "state_summary": "当前状态。" * 120,
        "core_context": {
            "protagonist_snapshot": {
                "name": "林渡",
                "location": "演武场",
                "power": {"realm": "炼气", "layer": 9},
                "golden_finger": {"name": "面板", "level": 2},
            }
        },
        "scene_context": {"appearing_characters": [{"entity_id": "elder_han", "last_seen_chapter": 1}]},
        "memory_context": {
            "previous_chapter_memory_card": {
                "summary": "上章留下强钩子。" * 20,
                "next_chapter_bridge": "必须接住上章强钩子。" * 10,
                "unresolved_questions": ["为什么是他"] * 5,
                "key_facts": ["灵碑异动"] * 5,
            },
            "active_plot_threads": [{"title": "灵碑异动", "status": "active", "priority": 90}] * 4,
            "recent_timeline_anchors": [{"chapter": 1, "anchor_time": "比试前夜", "countdown": "D-1"}] * 3,
            "related_entity_state_changes": [{"entity_id": "hero", "field": "risk", "old_value": "1", "new_value": "2", "chapter": 1}] * 3,
            "candidate_facts": [{"fact": "长老已经起疑", "entity_id": "elder_han", "confidence": 0.4}] * 3,
        },
        "reader_signal": {
            "recent_reading_power": [{"hook_type": "悬念钩"}],
            "review_trend": {"overall_avg": 81},
        },
        "genre_profile": {"genre": "xianxia", "reference_hints": ["升级线清晰", "回报前置"]},
        "golden_three_contract": {
            "enabled": True,
            "golden_three_role": "接住首章钩子并升级代价/规则",
            "opening_window_chars": 500,
            "opening_trigger": "前500字回应首章钩子",
            "reader_promise": "退婚反杀 + 系统加点",
            "must_deliver_this_chapter": ["回应首章钩子", "升级代价", "给至少1个微兑现"],
            "micro_payoffs": ["第一次灵碑回应", "众人反应变化"],
            "end_hook_requirement": "把期待升级为必须看第3章",
            "forbidden_slow_zones": ["景物空镜", "世界观讲解"],
        },
        "writing_guidance": {
            "guidance_items": ["先修低分", "钩子差异化", "强化兑现", "压缩背景"],
            "checklist": [
                {"label": "回应首章钩子", "required": True},
                {"label": "升级代价", "required": True},
                {"label": "控制说明腔", "required": False},
            ],
            "signals_used": {"top_patterns": ["身份压制"]},
        },
        "rag_assist": {"hits": [{"chapter": 1, "content": "上一章已有灵碑异动"}]},
    }

    pack = build_execution_pack_payload(payload)
    assert len(json.dumps(pack, ensure_ascii=False)) < len(json.dumps(payload, ensure_ascii=False))


def test_build_review_pack_payload_embeds_absolute_paths_and_whitelist(tmp_path):

    from extract_chapter_context import build_chapter_context_payload, build_review_pack_payload
    from data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        "project": {"genre": "xianxia"},
        "project_info": {"title": "测试书", "genre": "xianxia"},
        "progress": {"current_chapter": 2, "total_words": 5000},
        "protagonist_state": {
            "name": "林渡",
            "power": {"realm": "炼气", "layer": 9},
            "location": "外门演武场",
        },
        "chapter_meta": {},
        "plot_threads": {"foreshadowing": []},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (cfg.ink_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    (cfg.ink_dir / "preferences.json").write_text(json.dumps({"opening_strategy": {"golden_three_enabled": True}}, ensure_ascii=False), encoding="utf-8")
    (cfg.ink_dir / "golden_three_plan.json").write_text(
        json.dumps({"enabled": True, "chapters": {"2": {"chapter": 2, "golden_three_role": "接住首章钩子"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    chapter_dir = tmp_path / "正文"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "第0002章-灵碑亮起.md").write_text("# 第2章\n林渡站在演武场中央。", encoding="utf-8")
    (chapter_dir / "第0001章-退婚广场，黑账初醒.md").write_text("# 第1章\n上一章正文。", encoding="utf-8")

    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / "第1卷 详细大纲.md").write_text("### 第2章：灵碑亮起\n本章必须接住上章钩子。", encoding="utf-8")

    settings_dir = tmp_path / "设定集" / "角色卡"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "林渡.md").write_text("林渡：隐忍冷静，不会无故失控。", encoding="utf-8")

    summaries_dir = cfg.ink_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    (summaries_dir / "ch0001.md").write_text("## 剧情摘要\n上一章总结", encoding="utf-8")

    payload = build_chapter_context_payload(tmp_path, 2)
    review_pack = build_review_pack_payload(tmp_path, 2, payload)

    assert review_pack["project_root"] == str(tmp_path.resolve())
    assert review_pack["chapter_file"].startswith(str(tmp_path.resolve()))
    assert review_pack["chapter_text"].startswith("# 第2章")
    assert review_pack["previous_chapters"][0]["chapter_file"].startswith(str(tmp_path.resolve()))
    assert review_pack["setting_snapshots"][0]["path"].startswith(str(tmp_path.resolve()))
    assert review_pack["allowed_read_files"]
    assert review_pack["chapter_file"] in review_pack["allowed_read_files"]
    assert str((cfg.ink_dir / "state.json").resolve()) in review_pack["allowed_read_files"]
    assert all(not path.endswith(".db") for path in review_pack["allowed_read_files"])


def test_render_text_contains_writing_guidance_section(tmp_path):

    from extract_chapter_context import _render_text

    payload = {
        "chapter": 10,
        "outline": "测试大纲",
        "previous_summaries": ["### 第9章摘要\n上一章"],
        "state_summary": "状态",
        "context_contract_version": "v3",
        "context_weight_stage": "early",
        "reader_signal": {"review_trend": {"overall_avg": 72}, "low_score_ranges": [{"start_chapter": 8, "end_chapter": 9}]},
        "genre_profile": {
            "genre": "xuanhuan",
            "genres": ["xuanhuan", "realistic"],
            "composite_hints": ["以玄幻主线推进，同时保留现实议题表达"],
            "reference_hints": ["升级线清晰"],
        },
        "golden_three_contract": {
            "enabled": True,
            "golden_three_role": "立触发",
            "opening_window_chars": 300,
            "reader_promise": "退婚反杀 + 系统加点",
            "opening_trigger": "前300字出现压制或利益冲突",
            "must_deliver_this_chapter": ["前300字强触发", "本章出现可见变化"],
            "end_hook_requirement": "章末必须留下强追更问题",
            "forbidden_slow_zones": ["景物空镜", "世界观讲解"],
        },
        "writing_guidance": {
            "guidance_items": ["先修低分", "钩子差异化"],
            "checklist": [
                {
                    "id": "fix_low_score_range",
                    "label": "修复低分区间问题",
                    "weight": 1.4,
                    "required": True,
                    "source": "reader_signal.low_score_ranges",
                    "verify_hint": "至少完成1处冲突升级",
                }
            ],
            "checklist_score": {
                "score": 81.5,
                "completion_rate": 0.66,
                "required_completion_rate": 0.75,
            },
            "methodology": {
                "enabled": True,
                "framework": "digital-serial-v1",
                "pilot": "xianxia",
                "genre_profile_key": "xianxia",
                "chapter_stage": "confront",
                "observability": {
                    "next_reason_clarity": 78.0,
                    "anchor_effectiveness": 74.0,
                    "rhythm_naturalness": 72.0,
                },
                "signals": {"risk_flags": ["pattern_overuse_watch"]},
            },
        },
    }

    text = _render_text(payload)
    assert "## 写作执行建议" in text
    assert "先修低分" in text
    assert "## Contract (v3)" in text
    assert "- 上下文阶段权重: early" in text
    assert "## 黄金三章契约" in text
    assert "- 本章职责: 立触发" in text
    assert "### 执行检查清单（可评分）" in text
    assert "- 总权重: 1.40" in text
    assert "[必做][w=1.4] 修复低分区间问题" in text
    assert "### 执行评分" in text
    assert "- 评分: 81.5" in text
    assert "- 复合题材: xuanhuan + realistic" in text
    assert "## 长篇方法论策略" in text
    assert "- 适用题材: xianxia" in text
    assert "next_reason=78.0" in text


def test_render_execution_pack_text_contains_core_sections():

    from extract_chapter_context import _render_execution_pack_text

    pack = {
        "chapter": 2,
        "title": "灵碑亮起",
        "mode": "golden_three",
        "taskbook": {
            "本章核心任务": ["必须交付：回应首章钩子"],
            "接住上章": ["上章摘要：林渡被长老盯上"],
            "出场角色": ["林渡：承接主线行动"],
            "场景与力量约束": ["地点：演武场"],
            "时间约束": ["Ch1；外门大比前夜；大比 D-1"],
            "风格指导": ["黄金三章模式：接住首章钩子并升级代价/规则"],
            "连续性与伏笔": ["活跃线程：灵碑异动；状态=active；优先级=90"],
            "追读力策略": ["读者承诺：退婚反杀 + 系统加点"],
        },
        "context_contract": {
            "目标": "接住首章灵碑异动",
            "阻力": "长老压制",
            "代价": "暴露底牌",
            "本章变化": "第一次公开拿到灵碑回应",
            "未闭合问题": "灵碑为什么只回应林渡",
            "核心冲突一句话": "林渡必须在暴露与隐忍之间取舍",
            "开头类型": "强触发开场：前500字回应灵碑异动",
            "情绪节奏": "前段施压，中后段兑现并留尾钩",
            "信息密度": "前500字优先冲突、承诺与主角压力，设定解释后置",
            "是否过渡章": False,
            "追读力设计": "章末要求=把期待升级为必须看第3章",
        },
        "step_2a_prompt": {
            "章节节拍": ["开场触发：前500字回应灵碑异动"],
            "不可变事实清单": ["上章结果：林渡被长老盯上"],
            "禁止事项": ["与大纲关键事件或设定规则冲突"],
            "终检清单": ["回应首章钩子"],
            "fail_conditions": ["未接住上章钩子/承诺"],
        },
    }

    text = _render_execution_pack_text(pack)
    assert "## 任务书（8板块）" in text
    assert "## Context Contract" in text
    assert "## Step 2A 直写提示" in text
    assert "回应首章钩子" in text


def test_render_text_contains_rag_assist_section_when_hits_exist(tmp_path):

    from extract_chapter_context import _render_text

    payload = {
        "chapter": 12,
        "outline": "测试大纲",
        "previous_summaries": [],
        "state_summary": "状态",
        "context_contract_version": "v3",
        "reader_signal": {},
        "genre_profile": {},
        "golden_three_contract": {},
        "writing_guidance": {},
        "rag_assist": {
            "invoked": True,
            "mode": "auto",
            "intent": "relationship",
            "query": "第12章 人物关系与动机：萧炎与药老发生冲突",
            "hits": [
                {
                    "chapter": 9,
                    "scene_index": 2,
                    "source": "graph_hybrid",
                    "score": 0.91,
                    "content": "萧炎与药老在修炼方向上发生分歧。",
                }
            ],
        },
    }

    text = _render_text(payload)
    assert "## RAG 检索线索" in text
    assert "- 模式: auto" in text
    assert "[graph_hybrid]" in text
    assert "萧炎与药老" in text
