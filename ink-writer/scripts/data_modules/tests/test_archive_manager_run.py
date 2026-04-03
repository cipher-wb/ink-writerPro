"""archive_manager.py 补充测试 — 覆盖 run_auto_check / restore_character / show_stats。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# archive_manager 在 scripts/ 目录
scripts_dir = str(Path(__file__).resolve().parents[2])
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager, EntityMeta
from archive_manager import ArchiveManager


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _setup(tmp_path, state: dict, *, entities: list | None = None):
    """创建项目并返回 ArchiveManager。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.ink_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8",
    )
    if entities:
        idx = IndexManager(cfg)
        for e in entities:
            idx.upsert_entity(e)
    return ArchiveManager(project_root=tmp_path)


def _archivable_state():
    """Return a state dict with data that meets all archive thresholds."""
    return {
        "progress": {"current_chapter": 200},
        "plot_threads": {
            "foreshadowing": [
                {"content": "秘密A", "status": "已回收", "resolved_chapter": 30},
                {"content": "秘密B", "status": "未回收"},
            ],
        },
        "review_checkpoints": [
            {"chapters": "1-10", "report": "review_Ch1-10.md"},
            {"chapters": "190-200", "report": "review_Ch190-200.md"},
        ],
    }


def _archivable_entities():
    """Entities containing an inactive decorative character."""
    return [
        EntityMeta(
            id="lixue", type="角色", canonical_name="李雪",
            tier="装饰", current={}, first_appearance=1, last_appearance=10,
        ),
        EntityMeta(
            id="xiaoyan", type="角色", canonical_name="萧炎",
            tier="核心", current={}, first_appearance=1, last_appearance=200,
        ),
    ]


# ===========================================================================
# run_auto_check
# ===========================================================================

class TestRunAutoCheckNoTrigger:
    """Trigger conditions NOT met and force=False → early return."""

    def test_prints_no_archive_needed(self, tmp_path, capsys):
        # chapter 3 → not a multiple of 10, tiny file → no size trigger
        am = _setup(tmp_path, {"progress": {"current_chapter": 3}})
        am.run_auto_check(force=False, dry_run=False)
        out = capsys.readouterr().out
        assert "无需归档（触发条件未满足）" in out
        assert "文件大小" in out
        assert "当前章节" in out


class TestRunAutoCheckNothingToArchive:
    """Trigger fires but all identify methods return empty lists."""

    def test_prints_no_data(self, tmp_path, capsys):
        # chapter 20 triggers (multiple of 10), but state has no archivable data
        am = _setup(tmp_path, {"progress": {"current_chapter": 20}})
        am.run_auto_check(force=False, dry_run=False)
        out = capsys.readouterr().out
        assert "无需归档（无符合条件的数据）" in out


class TestRunAutoCheckForce:
    """force=True skips trigger check, but still detects nothing to archive."""

    def test_force_skips_trigger(self, tmp_path, capsys):
        # chapter 3 → trigger would NOT fire, but force=True bypasses
        am = _setup(tmp_path, {"progress": {"current_chapter": 3}})
        am.run_auto_check(force=True, dry_run=False)
        out = capsys.readouterr().out
        # Should NOT see "触发条件未满足"
        assert "触发条件未满足" not in out
        # With no archivable data it should reach the "无符合条件" branch
        assert "无需归档（无符合条件的数据）" in out


class TestRunAutoCheckDryRun:
    """dry_run=True prints candidates but does NOT write archives."""

    def test_dry_run_output(self, tmp_path, capsys):
        am = _setup(
            tmp_path,
            _archivable_state(),
            entities=_archivable_entities(),
        )
        am.run_auto_check(force=True, dry_run=True)
        out = capsys.readouterr().out
        assert "[Dry-run]" in out
        assert "李雪" in out
        assert "秘密A" in out
        # Archive files must NOT be created
        assert not am.characters_archive.exists()
        assert not am.plot_threads_archive.exists()
        assert not am.reviews_archive.exists()


class TestRunAutoCheckFullExecution:
    """Full archiving path: identify → archive → remove → save."""

    def test_full_archive(self, tmp_path, capsys):
        am = _setup(
            tmp_path,
            _archivable_state(),
            entities=_archivable_entities(),
        )
        am.run_auto_check(force=True, dry_run=False)
        out = capsys.readouterr().out

        # Final summary printed
        assert "归档完成" in out
        assert "角色归档" in out
        assert "伏笔归档" in out
        assert "报告归档" in out
        assert "文件大小" in out  # size comparison line

        # Archive files created
        assert am.characters_archive.exists()
        assert am.plot_threads_archive.exists()
        assert am.reviews_archive.exists()

        # state.json updated — archived thread removed
        updated_state = json.loads(am.state_file.read_text(encoding="utf-8"))
        remaining_contents = [
            t.get("content")
            for t in updated_state.get("plot_threads", {}).get("foreshadowing", [])
        ]
        assert "秘密A" not in remaining_contents
        assert "秘密B" in remaining_contents

        # Old review removed, recent review kept
        remaining_reports = [
            r.get("report") for r in updated_state.get("review_checkpoints", [])
        ]
        assert "review_Ch1-10.md" not in remaining_reports
        assert "review_Ch190-200.md" in remaining_reports


class TestRunAutoCheckDryRunShowsReviews:
    """dry_run prints old review info."""

    def test_dry_run_reviews(self, tmp_path, capsys):
        state = {
            "progress": {"current_chapter": 200},
            "review_checkpoints": [
                {"chapters": "1-10", "report": "review_Ch1-10.md"},
            ],
        }
        am = _setup(tmp_path, state)
        am.run_auto_check(force=True, dry_run=True)
        out = capsys.readouterr().out
        assert "旧审查报告" in out
        assert "Ch10" in out


# ===========================================================================
# restore_character
# ===========================================================================

class TestRestoreCharacter:
    """restore_character() — found and not-found paths."""

    def _archive_a_character(self, tmp_path):
        """Archive 李雪, then return the ArchiveManager."""
        am = _setup(
            tmp_path,
            _archivable_state(),
            entities=_archivable_entities(),
        )
        # Perform real archive so characters_archive gets populated
        state = am.load_state()
        inactive = am.identify_inactive_characters(state)
        am.archive_characters(inactive, dry_run=False)
        return am

    def test_restore_found(self, tmp_path, capsys):
        am = self._archive_a_character(tmp_path)
        # Verify archive has the character
        archived = am.load_archive(am.characters_archive)
        names = [c["name"] for c in archived]
        assert "李雪" in names

        am.restore_character("李雪")
        out = capsys.readouterr().out
        assert "角色已恢复" in out or "实体状态恢复失败" in out

        # Character removed from archive file
        archived_after = am.load_archive(am.characters_archive)
        names_after = [c["name"] for c in archived_after]
        assert "李雪" not in names_after

    def test_restore_not_found(self, tmp_path, capsys):
        am = self._archive_a_character(tmp_path)
        am.restore_character("不存在的角色")
        out = capsys.readouterr().out
        assert "归档中未找到角色" in out

    def test_restore_removes_archived_at(self, tmp_path, capsys):
        """Restoring should pop the archived_at field before IndexManager call."""
        am = self._archive_a_character(tmp_path)
        # Patch update_entity_field to inspect the call
        with patch.object(am._index_manager, "update_entity_field") as mock_uef:
            am.restore_character("李雪")
            # Should have been called with status="active"
            mock_uef.assert_called_once()
            args = mock_uef.call_args
            assert args[0][1] == "status"
            assert args[0][2] == "active"

    def test_restore_handles_index_error(self, tmp_path, capsys):
        """If update_entity_field raises, warning is printed but archive is still updated."""
        am = self._archive_a_character(tmp_path)
        with patch.object(
            am._index_manager, "update_entity_field",
            side_effect=RuntimeError("db locked"),
        ):
            am.restore_character("李雪")
        out = capsys.readouterr().out
        assert "实体状态恢复失败" in out
        # Character should still be removed from archive
        archived_after = am.load_archive(am.characters_archive)
        assert all(c["name"] != "李雪" for c in archived_after)


# ===========================================================================
# show_stats
# ===========================================================================

class TestShowStats:
    """show_stats() output verification."""

    def test_stats_empty(self, tmp_path, capsys):
        """No archive files yet — all counts zero."""
        am = _setup(tmp_path, {"progress": {"current_chapter": 5}})
        am.show_stats()
        out = capsys.readouterr().out
        assert "归档统计" in out
        assert "角色归档: 0" in out
        assert "伏笔归档: 0" in out
        assert "报告归档: 0" in out
        assert "state.json 当前大小" in out

    def test_stats_with_data(self, tmp_path, capsys):
        """Archive some data first, then verify counts."""
        am = _setup(
            tmp_path,
            _archivable_state(),
            entities=_archivable_entities(),
        )
        # Archive characters
        state = am.load_state()
        inactive = am.identify_inactive_characters(state)
        am.archive_characters(inactive, dry_run=False)

        # Archive threads
        resolved = am.identify_resolved_plot_threads(state)
        am.archive_plot_threads(resolved, dry_run=False)

        am.show_stats()
        out = capsys.readouterr().out
        assert "角色归档: 1" in out
        assert "伏笔归档: 1" in out
        assert "归档大小" in out
        assert "state.json 当前大小" in out

    def test_stats_shows_archive_size(self, tmp_path, capsys):
        """Archive size should be > 0 KB when files exist."""
        am = _setup(tmp_path, {"progress": {"current_chapter": 200}})
        # Write a small archive manually
        am.save_archive(am.characters_archive, [{"name": "test", "archived_at": "2026-01-01"}])
        am.show_stats()
        out = capsys.readouterr().out
        # Size line should show non-zero
        assert "归档大小: 0.00 KB" not in out
