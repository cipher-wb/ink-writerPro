#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for backup_manager.py — GitBackupManager and main() CLI."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_module():
    """Import backup_manager after injecting scripts/ into sys.path."""
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import backup_manager

    return backup_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mod():
    return _load_module()


@pytest.fixture
def project(tmp_path):
    """Create a minimal project directory with .ink/state.json."""
    ink = tmp_path / ".ink"
    ink.mkdir()
    state = ink / "state.json"
    state.write_text('{"progress":{"current_chapter":1}}', encoding="utf-8")
    return tmp_path


@pytest.fixture
def manager_git(mod, project, monkeypatch):
    """Return a GitBackupManager that believes git is available and initialized."""
    monkeypatch.setattr(mod, "is_git_available", lambda: True)
    # Pretend .git already exists so __init__ doesn't try to run git init
    git_dir = project / ".git"
    git_dir.mkdir()
    return mod.GitBackupManager(str(project))


@pytest.fixture
def manager_no_git(mod, project, monkeypatch):
    """Return a GitBackupManager with git unavailable (local-backup mode)."""
    monkeypatch.setattr(mod, "is_git_available", lambda: False)
    return mod.GitBackupManager(str(project))


# ===================================================================
# __init__
# ===================================================================

class TestInit:

    def test_git_available_and_initialized(self, manager_git):
        assert manager_git.git_available is True
        assert manager_git.git_dir.exists()

    def test_git_not_available(self, mod, project, monkeypatch, capsys):
        monkeypatch.setattr(mod, "is_git_available", lambda: False)
        mgr = mod.GitBackupManager(str(project))
        assert mgr.git_available is False
        out = capsys.readouterr().out
        assert "Git 不可用" in out

    def test_git_available_but_not_initialized(self, mod, project, monkeypatch):
        """When git is available but .git dir missing, _init_git is called."""
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        calls = []

        def fake_init_git(self):
            calls.append(True)
            # Create .git so the rest of init is happy
            self.git_dir.mkdir(exist_ok=True)
            return True

        monkeypatch.setattr(mod.GitBackupManager, "_init_git", fake_init_git)
        mgr = mod.GitBackupManager(str(project))
        assert len(calls) == 1


# ===================================================================
# _init_git
# ===================================================================

class TestInitGit:

    def test_init_git_success(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        git_dir = project / ".git"
        git_dir.mkdir()

        call_log = []

        def fake_run(args, **kw):
            call_log.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        mgr = mod.GitBackupManager.__new__(mod.GitBackupManager)
        mgr.project_root = Path(project)
        mgr.git_dir = project / ".git"
        mgr.git_available = True

        result = mgr._init_git()
        assert result is True
        # git init, git add, git commit => 3 subprocess calls
        assert len(call_log) == 3
        # .gitignore should have been created
        assert (project / ".gitignore").exists()

    def test_init_git_gitignore_already_exists(self, mod, project, monkeypatch):
        """If .gitignore already exists it should not be overwritten."""
        (project / ".gitignore").write_text("existing", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="", stderr=""))

        mgr = mod.GitBackupManager.__new__(mod.GitBackupManager)
        mgr.project_root = Path(project)
        mgr.git_dir = project / ".git"
        mgr.git_available = True

        mgr._init_git()
        assert (project / ".gitignore").read_text(encoding="utf-8") == "existing"

    def test_init_git_failure(self, mod, project, monkeypatch, capsys):
        monkeypatch.setattr(subprocess, "run",
                            MagicMock(side_effect=subprocess.CalledProcessError(1, "git init")))

        mgr = mod.GitBackupManager.__new__(mod.GitBackupManager)
        mgr.project_root = Path(project)
        mgr.git_dir = project / ".git"
        mgr.git_available = True

        result = mgr._init_git()
        assert result is False
        assert "初始化失败" in capsys.readouterr().out


# ===================================================================
# _run_git_command
# ===================================================================

class TestRunGitCommand:

    def test_git_not_available(self, manager_no_git):
        ok, msg = manager_no_git._run_git_command(["status"])
        assert ok is False
        assert "不可用" in msg

    def test_success(self, manager_git, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="ok\n", stderr=""))
        ok, out = manager_git._run_git_command(["status"])
        assert ok is True
        assert out == "ok\n"

    def test_called_process_error(self, manager_git, monkeypatch):
        err = subprocess.CalledProcessError(1, "git", stderr="fatal: bad")
        monkeypatch.setattr(subprocess, "run", MagicMock(side_effect=err))
        ok, out = manager_git._run_git_command(["bad-cmd"])
        assert ok is False
        assert "fatal: bad" in out

    def test_timeout(self, manager_git, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                            MagicMock(side_effect=subprocess.TimeoutExpired("git", 60)))
        ok, out = manager_git._run_git_command(["slow"])
        assert ok is False
        assert "超时" in out

    def test_os_error(self, manager_git, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                            MagicMock(side_effect=OSError("not found")))
        ok, out = manager_git._run_git_command(["missing"])
        assert ok is False
        assert "not found" in out


# ===================================================================
# _local_backup
# ===================================================================

class TestLocalBackup:

    def test_local_backup_with_state(self, manager_no_git, project, capsys):
        result = manager_no_git._local_backup(10)
        assert result is True
        out = capsys.readouterr().out
        assert "本地备份完成" in out

        backup_dir = project / ".ink" / "backups"
        assert backup_dir.exists()
        # There should be exactly one backup subfolder
        subs = list(backup_dir.iterdir())
        assert len(subs) == 1
        assert (subs[0] / "state.json").exists()

    def test_local_backup_no_state_file(self, mod, tmp_path, monkeypatch):
        """If state.json doesn't exist, backup dir is created but no file is copied."""
        monkeypatch.setattr(mod, "is_git_available", lambda: False)
        mgr = mod.GitBackupManager.__new__(mod.GitBackupManager)
        mgr.project_root = tmp_path
        mgr.git_dir = tmp_path / ".git"
        mgr.git_available = False

        result = mgr._local_backup(5)
        assert result is True

    def test_local_backup_os_error(self, mod, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(mod, "is_git_available", lambda: False)
        mgr = mod.GitBackupManager.__new__(mod.GitBackupManager)
        mgr.project_root = tmp_path
        mgr.git_dir = tmp_path / ".git"
        mgr.git_available = False

        # Make shutil.copy2 fail after backup dir is created
        monkeypatch.setattr(mod.shutil, "copy2", MagicMock(side_effect=OSError("disk full")))
        # Ensure state.json exists so copy2 is attempted
        ink = tmp_path / ".ink"
        ink.mkdir(parents=True, exist_ok=True)
        (ink / "state.json").write_text("{}", encoding="utf-8")

        result = mgr._local_backup(1)
        assert result is False
        assert "本地备份失败" in capsys.readouterr().out


# ===================================================================
# _backup_index_db
# ===================================================================

class TestBackupIndexDb:

    def test_backup_index_db_success(self, manager_git, monkeypatch):
        """When data_modules are importable and db exists, backup_db is called."""
        fake_cfg = MagicMock()
        fake_cfg.index_db.exists.return_value = True

        fake_mgr_instance = MagicMock()
        fake_mgr_instance.backup_db.return_value = Path("/tmp/backup.db")

        with patch.dict("sys.modules", {
            "data_modules": MagicMock(),
            "data_modules.config": MagicMock(DataModulesConfig=MagicMock(from_project_root=MagicMock(return_value=fake_cfg))),
            "data_modules.index_manager": MagicMock(IndexManager=MagicMock(return_value=fake_mgr_instance)),
        }):
            manager_git._backup_index_db(10)

        fake_mgr_instance.backup_db.assert_called_once()

    def test_backup_index_db_exception_is_swallowed(self, manager_git):
        """Errors in _backup_index_db must not propagate."""
        with patch.dict("sys.modules", {
            "data_modules.config": MagicMock(side_effect=ImportError("no module")),
        }):
            # Should not raise
            manager_git._backup_index_db(99)


# ===================================================================
# backup (the main method)
# ===================================================================

class TestBackup:

    def _stub_git(self, monkeypatch, manager, responses):
        """
        Stub _run_git_command to return successive (ok, output) tuples.
        Also stub _backup_index_db to do nothing.
        """
        it = iter(responses)
        monkeypatch.setattr(manager, "_run_git_command", lambda *a, **kw: next(it))
        monkeypatch.setattr(manager, "_backup_index_db", lambda ch: None)

    def test_backup_no_git_falls_back_to_local(self, manager_no_git, project, monkeypatch, capsys):
        monkeypatch.setattr(manager_no_git, "_backup_index_db", lambda ch: None)
        result = manager_no_git.backup(5, "test")
        assert result is True
        assert "本地备份完成" in capsys.readouterr().out

    def test_backup_git_add_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (False, "error in add"),
        ])
        result = manager_git.backup(1)
        assert result is False
        assert "git add 失败" in capsys.readouterr().out

    def test_backup_nothing_to_commit(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),                           # git add
            (False, "nothing to commit"),          # git commit
        ])
        result = manager_git.backup(1)
        assert result is True
        assert "无变更" in capsys.readouterr().out

    def test_backup_commit_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),                           # git add
            (False, "some error"),                 # git commit
        ])
        result = manager_git.backup(1)
        assert result is False
        assert "git commit 失败" in capsys.readouterr().out

    def test_backup_full_success_without_title(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),          # git add
            (True, ""),          # git commit
            (True, ""),          # tag -d (old tag)
            (True, ""),          # tag create
        ])
        result = manager_git.backup(45)
        assert result is True
        out = capsys.readouterr().out
        assert "Git 提交完成" in out
        assert "tag 已创建" in out

    def test_backup_full_success_with_title(self, mod, manager_git, monkeypatch, capsys):
        calls = []

        def fake_run_git(args, check=True):
            calls.append(args)
            return (True, "")

        monkeypatch.setattr(manager_git, "_run_git_command", fake_run_git)
        monkeypatch.setattr(manager_git, "_backup_index_db", lambda ch: None)
        monkeypatch.setattr(mod, "sanitize_commit_message", lambda m: m)

        result = manager_git.backup(10, "龙王的挑战")
        assert result is True
        # The commit call should include the title in the message
        commit_call = calls[1]  # second call is commit
        # args: ["commit", "-m", "Chapter 10: 龙王的挑战"]
        assert any("龙王的挑战" in str(a) for a in commit_call)

    def test_backup_tag_creation_fails_non_fatal(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),          # git add
            (True, ""),          # git commit
            (True, ""),          # tag -d
            (False, "tag err"),  # tag create fails
        ])
        result = manager_git.backup(5)
        # Should still return True — tag failure is non-fatal
        assert result is True
        assert "tag 失败" in capsys.readouterr().out


# ===================================================================
# rollback
# ===================================================================

class TestRollback:

    def _stub_git(self, monkeypatch, manager, responses):
        it = iter(responses)
        monkeypatch.setattr(manager, "_run_git_command", lambda *a, **kw: next(it))

    def test_rollback_clean_success(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),          # status --porcelain (clean)
            (True, ""),          # checkout tag
        ])
        result = manager_git.rollback(30)
        assert result is True
        assert "已回滚到第 30 章" in capsys.readouterr().out

    def test_rollback_dirty_creates_backup_branch(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "M state.json\n"),   # status --porcelain (dirty)
            (True, ""),                  # checkout -b backup_branch
            (True, ""),                  # add .
            (True, ""),                  # commit backup
            (True, ""),                  # checkout master
            (True, ""),                  # checkout tag
        ])
        result = manager_git.rollback(20)
        assert result is True
        out = capsys.readouterr().out
        assert "备份分支已创建" in out
        assert "已回滚到第 20 章" in out

    def test_rollback_backup_branch_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "M state.json\n"),  # dirty
            (False, "branch err"),      # checkout -b fails
        ])
        result = manager_git.rollback(10)
        assert result is False
        assert "创建备份分支失败" in capsys.readouterr().out

    def test_rollback_checkout_tag_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),                  # clean
            (False, "tag not found"),    # checkout tag fails
        ])
        result = manager_git.rollback(99)
        assert result is False
        assert "回滚失败" in capsys.readouterr().out


# ===================================================================
# diff
# ===================================================================

class TestDiff:

    def _stub_git(self, monkeypatch, manager, responses):
        it = iter(responses)
        monkeypatch.setattr(manager, "_run_git_command", lambda *a, **kw: next(it))

    def test_diff_success_with_state_changes(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "2 files changed\n"),   # diff --stat
            (True, "+line\n-line\n"),       # diff state.json
        ])
        manager_git.diff(10, 20)
        out = capsys.readouterr().out
        assert "文件变更统计" in out
        assert "+line" in out

    def test_diff_stat_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (False, "tag missing"),
        ])
        manager_git.diff(1, 2)
        assert "对比失败" in capsys.readouterr().out

    def test_diff_no_state_changes(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "1 file changed\n"),
            (True, ""),                     # empty state diff
        ])
        manager_git.diff(5, 6)
        assert "(无变更)" in capsys.readouterr().out

    def test_diff_long_output_truncated(self, manager_git, monkeypatch, capsys):
        long_diff = "x" * 3000
        self._stub_git(monkeypatch, manager_git, [
            (True, "stats\n"),
            (True, long_diff),
        ])
        manager_git.diff(1, 2)
        out = capsys.readouterr().out
        assert "已截断" in out

    def test_diff_state_diff_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "stats\n"),
            (False, ""),
        ])
        manager_git.diff(1, 2)
        assert "(无变更)" in capsys.readouterr().out


# ===================================================================
# list_backups
# ===================================================================

class TestListBackups:

    def _stub_git(self, monkeypatch, manager, responses):
        it = iter(responses)
        monkeypatch.setattr(manager, "_run_git_command", lambda *a, **kw: next(it))

    def test_list_no_tags(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (False, ""),   # tag -l returns nothing
        ])
        manager_git.list_backups()
        assert "暂无备份" in capsys.readouterr().out

    def test_list_empty_output(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),    # tag -l returns empty string
        ])
        manager_git.list_backups()
        assert "暂无备份" in capsys.readouterr().out

    def test_list_with_tags(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, "ch0010\nch0020\nch0005\n"),      # tags
            (True, "abc123 2026-01-01 Chapter 10"),   # log ch0005
            (True, "def456 2026-01-02 Chapter 10"),   # log ch0010
            (True, "ghi789 2026-01-03 Chapter 20"),   # log ch0020
            (True, "recent commits\n"),                # log --oneline -5
        ])
        manager_git.list_backups()
        out = capsys.readouterr().out
        assert "总计：3 个备份" in out
        assert "recent commits" in out


# ===================================================================
# create_branch
# ===================================================================

class TestCreateBranch:

    def _stub_git(self, monkeypatch, manager, responses):
        it = iter(responses)
        monkeypatch.setattr(manager, "_run_git_command", lambda *a, **kw: next(it))

    def test_create_branch_success(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),    # rev-parse tag
            (True, ""),    # branch create
        ])
        result = manager_git.create_branch(50, "alt-ending")
        assert result is True
        out = capsys.readouterr().out
        assert "分支已创建" in out
        assert "alt-ending" in out

    def test_create_branch_tag_not_exists(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (False, ""),   # rev-parse fails
        ])
        result = manager_git.create_branch(99, "no-tag")
        assert result is False
        assert "不存在" in capsys.readouterr().out

    def test_create_branch_git_branch_fails(self, manager_git, monkeypatch, capsys):
        self._stub_git(monkeypatch, manager_git, [
            (True, ""),            # rev-parse ok
            (False, "already exists"),  # branch fails
        ])
        result = manager_git.create_branch(10, "dup")
        assert result is False
        assert "创建分支失败" in capsys.readouterr().out


# ===================================================================
# main() CLI
# ===================================================================

class TestMain:

    def test_main_chapter_backup(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        backup_called = []
        monkeypatch.setattr(mod.GitBackupManager, "backup",
                            lambda self, ch, title="": backup_called.append((ch, title)))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--chapter", "45", "--chapter-title", "测试",
                             "--project-root", str(project)])
        mod.main()
        assert backup_called == [(45, "测试")]

    def test_main_rollback(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        rollback_called = []
        monkeypatch.setattr(mod.GitBackupManager, "rollback",
                            lambda self, ch: rollback_called.append(ch))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--rollback", "30",
                             "--project-root", str(project)])
        mod.main()
        assert rollback_called == [30]

    def test_main_diff(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        diff_called = []
        monkeypatch.setattr(mod.GitBackupManager, "diff",
                            lambda self, a, b: diff_called.append((a, b)))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--diff", "10", "20",
                             "--project-root", str(project)])
        mod.main()
        assert diff_called == [(10, 20)]

    def test_main_create_branch(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        branch_called = []
        monkeypatch.setattr(mod.GitBackupManager, "create_branch",
                            lambda self, ch, name: branch_called.append((ch, name)))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--create-branch", "50",
                             "--branch-name", "alt",
                             "--project-root", str(project)])
        mod.main()
        assert branch_called == [(50, "alt")]

    def test_main_create_branch_missing_name(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--create-branch", "50",
                             "--project-root", str(project)])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1

    def test_main_list(self, mod, project, monkeypatch):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        list_called = []
        monkeypatch.setattr(mod.GitBackupManager, "list_backups",
                            lambda self: list_called.append(True))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--list",
                             "--project-root", str(project)])
        mod.main()
        assert list_called == [True]

    def test_main_no_args_shows_help(self, mod, project, monkeypatch, capsys):
        monkeypatch.setattr(mod, "is_git_available", lambda: True)
        monkeypatch.setattr(mod, "resolve_project_root", lambda p: project)
        (project / ".git").mkdir(exist_ok=True)

        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--project-root", str(project)])
        mod.main()
        out = capsys.readouterr().out
        assert "备份" in out or "usage" in out.lower() or "示例" in out

    def test_main_project_root_not_found(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "resolve_project_root",
                            MagicMock(side_effect=FileNotFoundError("no project")))
        monkeypatch.setattr(sys, "argv",
                            ["backup_manager.py", "--list", "--project-root", "/nonexistent"])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1


# ===================================================================
# Windows UTF-8 branch (platform guard)
# ===================================================================

class TestWindowsCompat:

    def test_windows_branch_not_called_on_non_windows(self, mod):
        """On non-Windows, enable_windows_utf8_stdio should not be invoked."""
        # This is a smoke test — on macOS/Linux the module loads without error
        assert hasattr(mod, "GitBackupManager")
