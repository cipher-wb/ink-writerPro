"""status_reporter.py 补充测试 — 覆盖 scan_chapters, analyze_characters,
analyze_strand_weave, generate_report 及各 section 生成器。"""

import json

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.index.index_manager import (
    IndexManager,
    EntityMeta,
    ChapterReadingPowerMeta,
)
from status_reporter import StatusReporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_project(tmp_path, state: dict, chapters: list[tuple[int, str, str]] | None = None):
    """创建项目目录 + state.json + 可选的正文文件。

    chapters: [(chapter_num, title, content), ...]
    """
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.ink_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    if chapters:
        chapters_dir = tmp_path / "正文"
        chapters_dir.mkdir(exist_ok=True)
        for num, title, content in chapters:
            fname = f"第{num:04d}章-{title}.md"
            (chapters_dir / fname).write_text(content, encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# StatusReporter 基础
# ---------------------------------------------------------------------------

class TestLoadState:
    def test_load_state_success(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 5}})
        r = StatusReporter(str(tmp_path))
        assert r.load_state() is True
        assert r.state["progress"]["current_chapter"] == 5

    def test_load_state_missing_file(self, tmp_path):
        r = StatusReporter(str(tmp_path))
        assert r.load_state() is False

    def test_cache_reading_power_eviction(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        r.load_state()
        # 填满缓存
        for i in range(r._CACHE_MAX_SIZE + 10):
            r._cache_reading_power(i, {"score": i})
        assert len(r._reading_power_cache) <= r._CACHE_MAX_SIZE


class TestExtractStatsField:
    def test_extracts_known_field(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        content = "- **主导Strand**: quest\n- **爽点**: 打脸"
        assert r._extract_stats_field(content, "主导Strand") == "quest"
        assert r._extract_stats_field(content, "爽点") == "打脸"

    def test_returns_empty_for_missing_field(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert r._extract_stats_field("no fields here", "主导Strand") == ""


# ---------------------------------------------------------------------------
# scan_chapters
# ---------------------------------------------------------------------------

class TestScanChapters:
    def test_scan_chapters_basic(self, tmp_path):
        state = {
            "progress": {"current_chapter": 2, "total_words": 5000},
            "protagonist_state": {"name": "萧炎"},
        }
        chapters = [
            (1, "天才少年", "# 天才少年\n\n萧炎是萧家的天才。\n\n- **主导Strand**: quest\n- **爽点**: 天才觉醒"),
            (2, "约定", "# 约定\n\n萧炎和纳兰嫣然的三年之约。"),
        ]
        _setup_project(tmp_path, state, chapters)
        r = StatusReporter(str(tmp_path))
        r.load_state()
        r.scan_chapters()
        assert len(r.chapters_data) == 2
        assert r.chapters_data[0]["chapter"] == 1
        assert r.chapters_data[0]["dominant"] == "quest"
        assert r.chapters_data[0]["word_count"] > 0

    def test_scan_chapters_no_dir(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 0}})
        r = StatusReporter(str(tmp_path))
        r.load_state()
        r.scan_chapters()
        assert r.chapters_data == []

    def test_scan_chapters_character_detection(self, tmp_path):
        cfg = _setup_project(
            tmp_path,
            {"progress": {"current_chapter": 1}, "protagonist_state": {"name": "萧炎"}},
            [(1, "开篇", "萧炎走在路上，遇到了药老。")],
        )
        # 注册角色到 index.db
        idx = IndexManager(cfg)
        idx.upsert_entity(EntityMeta(
            id="xiaoyan", type="角色", canonical_name="萧炎",
            current={}, first_appearance=1, last_appearance=1,
        ))
        idx.upsert_entity(EntityMeta(
            id="yaolao", type="角色", canonical_name="药老",
            current={}, first_appearance=1, last_appearance=1,
        ))
        r = StatusReporter(str(tmp_path))
        r.load_state()
        r.scan_chapters()
        assert "萧炎" in r.chapters_data[0]["characters"]


# ---------------------------------------------------------------------------
# analyze_characters
# ---------------------------------------------------------------------------

class TestAnalyzeCharacters:
    def test_no_state(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        # 不调用 load_state
        assert r.analyze_characters() == {}

    def test_character_activity(self, tmp_path):
        cfg = _setup_project(tmp_path, {
            "progress": {"current_chapter": 50},
            "protagonist_state": {"name": "萧炎"},
        })
        idx = IndexManager(cfg)
        idx.upsert_entity(EntityMeta(
            id="xiaoyan", type="角色", canonical_name="萧炎",
            current={}, first_appearance=1, last_appearance=50,
        ))
        idx.upsert_entity(EntityMeta(
            id="lixue", type="角色", canonical_name="李雪",
            current={}, first_appearance=1, last_appearance=10,
        ))
        r = StatusReporter(str(tmp_path))
        r.load_state()
        activity = r.analyze_characters()
        assert activity["萧炎"]["status"] == "✅ 活跃"
        assert "掉线" in activity["李雪"]["status"]


# ---------------------------------------------------------------------------
# analyze_strand_weave
# ---------------------------------------------------------------------------

class TestAnalyzeStrandWeave:
    def test_no_data(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}, "strand_tracker": {}})
        r = StatusReporter(str(tmp_path))
        r.load_state()
        result = r.analyze_strand_weave()
        assert result.get("has_data") is False

    def test_balanced_strands(self, tmp_path):
        # 构造 10 章: 6 quest, 2 fire, 2 constellation
        history = (
            [{"strand": "quest"}] * 6
            + [{"strand": "fire"}] * 2
            + [{"strand": "constellation"}] * 2
        )
        _setup_project(tmp_path, {
            "progress": {"current_chapter": 10},
            "strand_tracker": {"history": history},
        })
        r = StatusReporter(str(tmp_path))
        r.load_state()
        result = r.analyze_strand_weave()
        assert result["has_data"] is True
        assert result["quest"]["count"] == 6
        assert result["fire"]["count"] == 2
        assert result["constellation"]["count"] == 2

    def test_quest_streak_violation(self, tmp_path):
        # 7 连续 quest 违规
        history = [{"strand": "quest"}] * 7
        _setup_project(tmp_path, {
            "progress": {"current_chapter": 7},
            "strand_tracker": {"history": history},
        })
        r = StatusReporter(str(tmp_path))
        r.load_state()
        result = r.analyze_strand_weave()
        assert len(result["violations"]) > 0
        assert result["max_quest_streak"] == 7

    def test_no_state(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert r.analyze_strand_weave() == {}


# ---------------------------------------------------------------------------
# _get_absence_status / _get_foreshadowing_status / _get_urgency_status
# ---------------------------------------------------------------------------

class TestStatusHelpers:
    def test_absence_active(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert r._get_absence_status(0) == "✅ 活跃"

    def test_absence_normal(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert "正常" in r._get_absence_status(5)

    def test_absence_critical(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert "严重" in r._get_absence_status(200)

    def test_foreshadowing_status(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert "正常" in r._get_foreshadowing_status(10)
        assert "严重" in r._get_foreshadowing_status(999)

    def test_urgency_expired(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert "超期" in r._get_urgency_status(5.0, -10)

    def test_urgency_normal(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert "正常" in r._get_urgency_status(0.5, 50)

    def test_pacing_rating(self, tmp_path):
        _setup_project(tmp_path, {"progress": {"current_chapter": 1}})
        r = StatusReporter(str(tmp_path))
        assert r._get_pacing_rating(None) == "数据不足"
        assert r._get_pacing_rating(800) == "优秀"
        assert r._get_pacing_rating(1200) == "良好"
        assert r._get_pacing_rating(1800) == "及格"
        assert r._get_pacing_rating(3000) == "偏低⚠️"


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_full_report(self, tmp_path):
        state = {
            "progress": {"current_chapter": 3, "total_words": 9000},
            "protagonist_state": {"name": "萧炎"},
            "project_info": {"target_words": 2000000},
            "plot_threads": {"foreshadowing": []},
            "strand_tracker": {"history": [
                {"strand": "quest"}, {"strand": "fire"}, {"strand": "quest"},
            ]},
        }
        cfg = _setup_project(tmp_path, state, [
            (1, "开篇", "萧炎的故事开始。" * 100),
            (2, "修炼", "萧炎开始修炼。" * 100),
            (3, "突破", "萧炎成功突破。" * 100),
        ])
        idx = IndexManager(cfg)
        idx.upsert_entity(EntityMeta(
            id="xiaoyan", type="角色", canonical_name="萧炎",
            current={}, first_appearance=1, last_appearance=3,
            is_protagonist=True,
        ))
        r = StatusReporter(str(tmp_path))
        r.load_state()
        r.scan_chapters()
        report = r.generate_report(focus="all")
        assert "# 全书健康报告" in report
        assert "基本数据" in report

    def test_basic_stats_section(self, tmp_path):
        _setup_project(tmp_path, {
            "progress": {"current_chapter": 10, "total_words": 40000},
            "project_info": {"target_words": 2000000},
        })
        r = StatusReporter(str(tmp_path))
        r.load_state()
        report = r.generate_report(focus="basic")
        assert "40,000" in report
        assert "10 章" in report

    def test_focus_characters(self, tmp_path):
        cfg = _setup_project(tmp_path, {
            "progress": {"current_chapter": 50},
            "protagonist_state": {"name": "萧炎"},
        })
        idx = IndexManager(cfg)
        idx.upsert_entity(EntityMeta(
            id="xiaoyan", type="角色", canonical_name="萧炎",
            current={}, first_appearance=1, last_appearance=50,
        ))
        r = StatusReporter(str(tmp_path))
        r.load_state()
        report = r.generate_report(focus="characters")
        assert "角色" in report

    def test_focus_strand(self, tmp_path):
        _setup_project(tmp_path, {
            "progress": {"current_chapter": 3},
            "strand_tracker": {"history": [
                {"strand": "quest"}, {"strand": "quest"}, {"strand": "quest"},
            ]},
        })
        r = StatusReporter(str(tmp_path))
        r.load_state()
        report = r.generate_report(focus="strand")
        assert "Strand" in report

    def test_focus_foreshadowing(self, tmp_path):
        _setup_project(tmp_path, {
            "progress": {"current_chapter": 100},
            "plot_threads": {"foreshadowing": [
                {"content": "秘密", "status": "未回收", "tier": "核心", "planted_chapter": 10, "target_chapter": 50},
            ]},
        })
        r = StatusReporter(str(tmp_path))
        r.load_state()
        report = r.generate_report(focus="foreshadowing")
        assert "伏笔" in report

    def test_report_no_state(self, tmp_path):
        r = StatusReporter(str(tmp_path))
        report = r.generate_report()
        assert "全书健康报告" in report
