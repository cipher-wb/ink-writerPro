"""archive_manager.py 补充测试 — 覆盖核心归档流程。"""

import json

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.index.index_manager import IndexManager, EntityMeta
from archive_manager import ArchiveManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _setup(tmp_path, state: dict, *, entities: list | None = None):
    """创建项目并返回 ArchiveManager。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.ink_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    if entities:
        idx = IndexManager(cfg)
        for e in entities:
            idx.upsert_entity(e)
    return ArchiveManager(project_root=tmp_path)


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

class TestLoadSaveState:
    def test_load_state(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 5}})
        state = am.load_state()
        assert state["progress"]["current_chapter"] == 5

    def test_load_state_missing(self, tmp_path):
        cfg = DataModulesConfig.from_project_root(tmp_path)
        cfg.ensure_dirs()
        am = ArchiveManager(project_root=tmp_path)
        with pytest.raises(SystemExit):
            am.load_state()


# ---------------------------------------------------------------------------
# check_trigger_conditions
# ---------------------------------------------------------------------------

class TestTriggerConditions:
    def test_chapter_trigger(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 20}})
        state = am.load_state()
        result = am.check_trigger_conditions(state)
        assert result["chapter_trigger"] is True
        assert result["should_archive"] is True

    def test_no_trigger(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 3}})
        state = am.load_state()
        result = am.check_trigger_conditions(state)
        assert result["chapter_trigger"] is False


# ---------------------------------------------------------------------------
# identify_inactive_characters
# ---------------------------------------------------------------------------

class TestIdentifyInactiveCharacters:
    def test_finds_inactive(self, tmp_path):
        entities = [
            EntityMeta(id="xiaoyan", type="角色", canonical_name="萧炎",
                       tier="核心", current={}, first_appearance=1, last_appearance=100),
            EntityMeta(id="lixue", type="角色", canonical_name="李雪",
                       tier="装饰", current={}, first_appearance=1, last_appearance=10),
            EntityMeta(id="wangwu", type="角色", canonical_name="王五",
                       tier="支线", current={}, first_appearance=1, last_appearance=90),
        ]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}}, entities=entities)
        state = am.load_state()
        inactive = am.identify_inactive_characters(state)
        names = [i["character"]["name"] for i in inactive]
        assert "李雪" in names  # 90 章不活跃
        assert "萧炎" not in names  # 核心角色不归档
        assert "王五" not in names  # 只有 10 章不活跃，不到 50 章阈值

    def test_no_inactive(self, tmp_path):
        entities = [
            EntityMeta(id="xiaoyan", type="角色", canonical_name="萧炎",
                       tier="装饰", current={}, first_appearance=1, last_appearance=100),
        ]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}}, entities=entities)
        state = am.load_state()
        assert am.identify_inactive_characters(state) == []


# ---------------------------------------------------------------------------
# identify_resolved_plot_threads
# ---------------------------------------------------------------------------

class TestIdentifyResolvedPlotThreads:
    def test_finds_archivable(self, tmp_path):
        state = {
            "progress": {"current_chapter": 100},
            "plot_threads": {
                "foreshadowing": [
                    {"content": "秘密A", "status": "已回收", "resolved_chapter": 30},
                    {"content": "秘密B", "status": "未回收"},
                    {"content": "秘密C", "status": "已回收", "resolved_chapter": 95},
                ],
            },
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        archivable = am.identify_resolved_plot_threads(s)
        contents = [a["thread"]["content"] for a in archivable]
        assert "秘密A" in contents  # 70 章前已回收
        assert "秘密B" not in contents  # 未回收
        assert "秘密C" not in contents  # 只有 5 章前回收，不到 20 章阈值

    def test_legacy_resolved_format(self, tmp_path):
        state = {
            "progress": {"current_chapter": 100},
            "plot_threads": {
                "resolved": [
                    {"content": "旧伏笔", "resolved_chapter": 10},
                ],
            },
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        archivable = am.identify_resolved_plot_threads(s)
        assert len(archivable) == 1

    def test_empty_plot_threads(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 50}})
        s = am.load_state()
        assert am.identify_resolved_plot_threads(s) == []


# ---------------------------------------------------------------------------
# identify_old_reviews
# ---------------------------------------------------------------------------

class TestIdentifyOldReviews:
    def test_finds_old_reviews(self, tmp_path):
        state = {
            "progress": {"current_chapter": 200},
            "review_checkpoints": [
                {"chapters": "1-10", "report": "review_Ch1-10.md"},
                {"chapters": "190-200", "report": "review_Ch190-200.md"},
            ],
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        old = am.identify_old_reviews(s)
        assert len(old) == 1
        assert old[0]["review"]["chapters"] == "1-10"

    def test_legacy_chapter_range(self, tmp_path):
        state = {
            "progress": {"current_chapter": 100},
            "review_checkpoints": [
                {"chapter_range": [1, 10]},
            ],
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        old = am.identify_old_reviews(s)
        assert len(old) == 1

    def test_no_reviews(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}})
        s = am.load_state()
        assert am.identify_old_reviews(s) == []


# ---------------------------------------------------------------------------
# archive_* 方法
# ---------------------------------------------------------------------------

class TestArchiveActions:
    def test_archive_characters_dry_run(self, tmp_path):
        entities = [
            EntityMeta(id="lixue", type="角色", canonical_name="李雪",
                       tier="装饰", current={}, first_appearance=1, last_appearance=10),
        ]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}}, entities=entities)
        state = am.load_state()
        inactive = am.identify_inactive_characters(state)
        count = am.archive_characters(inactive, dry_run=True)
        assert count >= 1
        # dry_run 不写文件
        assert not am.characters_archive.exists()

    def test_archive_characters_real(self, tmp_path):
        entities = [
            EntityMeta(id="lixue", type="角色", canonical_name="李雪",
                       tier="装饰", current={}, first_appearance=1, last_appearance=10),
        ]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}}, entities=entities)
        state = am.load_state()
        inactive = am.identify_inactive_characters(state)
        count = am.archive_characters(inactive, dry_run=False)
        assert count >= 1
        assert am.characters_archive.exists()
        archived = json.loads(am.characters_archive.read_text())
        assert len(archived) >= 1

    def test_archive_plot_threads(self, tmp_path):
        resolved = [{"thread": {"content": "秘密"}, "chapters_since_resolved": 70, "resolved_chapter": 30}]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}})
        count = am.archive_plot_threads(resolved, dry_run=False)
        assert count == 1
        assert am.plot_threads_archive.exists()

    def test_archive_reviews(self, tmp_path):
        old = [{"review": {"chapters": "1-10"}, "chapters_since_review": 90, "review_chapter": 10}]
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}})
        count = am.archive_reviews(old, dry_run=False)
        assert count == 1
        assert am.reviews_archive.exists()

    def test_archive_empty_list_returns_zero(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 100}})
        assert am.archive_characters([], dry_run=False) == 0
        assert am.archive_plot_threads([], dry_run=False) == 0
        assert am.archive_reviews([], dry_run=False) == 0


# ---------------------------------------------------------------------------
# remove_from_state
# ---------------------------------------------------------------------------

class TestRemoveFromState:
    def test_remove_resolved_threads(self, tmp_path):
        state = {
            "progress": {"current_chapter": 100},
            "plot_threads": {
                "foreshadowing": [
                    {"content": "秘密A", "status": "已回收", "resolved_chapter": 30},
                    {"content": "秘密B", "status": "未回收"},
                ],
            },
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        resolved = [{"thread": {"content": "秘密A"}, "chapters_since_resolved": 70, "resolved_chapter": 30}]
        updated = am.remove_from_state(s, [], resolved, [])
        contents = [t["content"] for t in updated["plot_threads"]["foreshadowing"]]
        assert "秘密A" not in contents
        assert "秘密B" in contents

    def test_remove_old_reviews(self, tmp_path):
        state = {
            "progress": {"current_chapter": 200},
            "review_checkpoints": [
                {"report": "review_Ch1-10.md"},
                {"report": "review_Ch190-200.md"},
            ],
        }
        am = _setup(tmp_path, state)
        s = am.load_state()
        old = [{"review": {"report": "review_Ch1-10.md"}, "chapters_since_review": 190, "review_chapter": 10}]
        updated = am.remove_from_state(s, [], [], old)
        reports = [r["report"] for r in updated["review_checkpoints"]]
        assert "review_Ch1-10.md" not in reports
        assert "review_Ch190-200.md" in reports


# ---------------------------------------------------------------------------
# load_archive / save_archive
# ---------------------------------------------------------------------------

class TestArchiveIO:
    def test_load_missing_archive(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 1}})
        assert am.load_archive(am.characters_archive) == []

    def test_save_and_load(self, tmp_path):
        am = _setup(tmp_path, {"progress": {"current_chapter": 1}})
        data = [{"name": "李雪", "archived_at": "2026-01-01"}]
        am.save_archive(am.characters_archive, data)
        loaded = am.load_archive(am.characters_archive)
        assert loaded[0]["name"] == "李雪"
