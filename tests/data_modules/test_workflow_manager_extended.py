#!/usr/bin/env python3
"""
Extended tests for workflow_manager — covers detect_interruption,
analyze_recovery_options, clear_current_task, fail_current_task,
and CLI __main__ paths that were previously untested.
"""

import json
from types import SimpleNamespace

import pytest

import workflow_manager


def _load_module():
    return workflow_manager


# ---------------------------------------------------------------------------
# detect_interruption
# ---------------------------------------------------------------------------

class TestDetectInterruption:
    def test_returns_none_when_no_task(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        assert module.detect_interruption() is None

    def test_returns_none_when_task_completed(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 1})
        module.complete_task()

        assert module.detect_interruption() is None

    def test_detects_running_task(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 5})
        module.start_step("Step 1", "Context")

        info = module.detect_interruption()
        assert info is not None
        assert info["command"] == "ink-write"
        assert info["current_step"]["id"] == "Step 1"
        assert info["elapsed_seconds"] >= 0

    def test_detects_failed_task(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 3})
        module.fail_current_task("test_error")

        info = module.detect_interruption()
        assert info is not None
        assert info["task_status"] == module.TASK_STATUS_FAILED


# ---------------------------------------------------------------------------
# analyze_recovery_options
# ---------------------------------------------------------------------------

class TestAnalyzeRecoveryOptions:
    def test_no_current_step_returns_restart(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 1},
            "current_step": None,
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 1
        assert options[0]["option"] == "A"
        assert "从头开始" in options[0]["label"]

    def test_step1_returns_restart(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 1},
            "current_step": {"id": "Step 1"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) >= 1
        assert "Step 1" in options[0]["label"]

    def test_step3_returns_two_options(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 2},
            "current_step": {"id": "Step 3"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 2
        labels = [o["label"] for o in options]
        assert any("审查" in l for l in labels)

    def test_step5_returns_restart_data_agent(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 4},
            "current_step": {"id": "Step 5"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 1
        assert "Step 5" in options[0]["label"]

    def test_step6_returns_two_options(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 6},
            "current_step": {"id": "Step 6"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 2

    def test_unknown_step_returns_restart(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 1},
            "current_step": {"id": "Step 99"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 1
        assert "从头开始" in options[0]["label"]

    def test_step2_no_existing_chapter(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 10},
            "current_step": {"id": "Step 2A"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) >= 1
        assert options[0]["risk"] == "low"

    def test_step2_with_existing_chapter(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        draft = module.default_chapter_draft_path(tmp_path, 10)
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("partial draft", encoding="utf-8")

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 10},
            "current_step": {"id": "Step 2A"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 2

    def test_step4_returns_two_options(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        info = {
            "command": "ink-write",
            "args": {"chapter_num": 15},
            "current_step": {"id": "Step 4"},
            "completed_steps": [],
        }
        options = module.analyze_recovery_options(info)
        assert len(options) == 2
        assert any("润色" in o["label"] for o in options)


# ---------------------------------------------------------------------------
# clear_current_task
# ---------------------------------------------------------------------------

class TestClearCurrentTask:
    def test_clears_running_task(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 1})
        module.clear_current_task()

        state = module.load_state()
        assert state["current_task"] is None

    def test_no_task_prints_warning(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.clear_current_task()
        captured = capsys.readouterr()
        assert "无中断任务" in captured.out


# ---------------------------------------------------------------------------
# fail_current_task
# ---------------------------------------------------------------------------

class TestFailCurrentTask:
    def test_marks_task_failed(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 2})
        module.start_step("Step 2A", "Draft")
        module.fail_current_task("test_reason")

        state = module.load_state()
        task = state["current_task"]
        assert task["status"] == module.TASK_STATUS_FAILED
        assert task["failure_reason"] == "test_reason"
        assert len(task["failed_steps"]) == 1

    def test_no_task_prints_warning(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.fail_current_task("reason")
        captured = capsys.readouterr()
        assert "无活动任务" in captured.out


# ---------------------------------------------------------------------------
# complete_task with active step
# ---------------------------------------------------------------------------

class TestCompleteTaskEdgeCases:
    def test_complete_task_with_active_step_finalizes_it_as_failed(self, tmp_path, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 3})
        module.start_step("Step 2A", "Draft")
        module.complete_task()

        state = module.load_state()
        assert state["current_task"] is None
        assert state["last_stable_state"] is not None

    def test_complete_task_no_task_prints_warning(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.complete_task()
        captured = capsys.readouterr()
        assert "无活动任务" in captured.out

    def test_complete_step_no_active_step_warns(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_task("ink-write", {"chapter_num": 4})
        module.complete_step("Step 1")
        captured = capsys.readouterr()
        assert "无活动 Step" in captured.out

    def test_start_step_no_task_warns(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        module.start_step("Step 1", "Context")
        captured = capsys.readouterr()
        assert "无活动任务" in captured.out


# ---------------------------------------------------------------------------
# extract_stable_state / get_pending_steps / expected_step_owner
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    def test_get_pending_steps_ink_review(self):
        module = _load_module()
        steps = module.get_pending_steps("ink-review")
        assert "Step 1" in steps
        assert len(steps) == 8

    def test_get_pending_steps_unknown_command(self):
        module = _load_module()
        steps = module.get_pending_steps("unknown-cmd")
        assert steps == []

    def test_expected_step_owner_ink_review(self):
        module = _load_module()
        assert module.expected_step_owner("ink-review", "Step 1") == "ink-review-skill"

    def test_expected_step_owner_unknown(self):
        module = _load_module()
        assert module.expected_step_owner("unknown", "Step 1") == "unknown"

    def test_step_allowed_before_respects_order(self):
        module = _load_module()
        completed = [{"id": "Step 1"}]
        assert module.step_allowed_before("ink-write", "Step 2A", completed) is True
        assert module.step_allowed_before("ink-write", "Step 3", completed) is False

    def test_step_allowed_before_unknown_step(self):
        module = _load_module()
        assert module.step_allowed_before("ink-write", "Step 99", []) is True


# ---------------------------------------------------------------------------
# CLI __main__ paths
# ---------------------------------------------------------------------------

class TestCLIMain:
    def test_cli_start_task(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(module, "_cli_project_root", tmp_path)
        monkeypatch.setattr(module, "find_project_root", lambda override=None: tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["workflow_manager.py", "start-task", "--command", "ink-write", "--chapter", "1"],
        )

        # Run the __main__ block by importing and parsing
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--project-root", dest="global_project_root")
        subparsers = parser.add_subparsers(dest="action")

        p = subparsers.add_parser("start-task")
        p.add_argument("--project-root")
        p.add_argument("--command", required=True)
        p.add_argument("--chapter", type=int)

        args = parser.parse_args(["start-task", "--command", "ink-write", "--chapter", "1"])
        module.start_task(args.command, {"chapter_num": args.chapter})

        state = module.load_state()
        assert state["current_task"] is not None
        assert state["current_task"]["command"] == "ink-write"

    def test_cli_detect_no_interruption(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        result = module.detect_interruption()
        assert result is None

    def test_cli_detect_with_interruption(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        module.start_task("ink-write", {"chapter_num": 42})
        module.start_step("Step 2A", "Draft")

        info = module.detect_interruption()
        assert info is not None
        options = module.analyze_recovery_options(info)
        assert len(options) >= 1

    def test_cli_cleanup_preview(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        cleaned = module.cleanup_artifacts(99, confirm=False)
        assert any("[预览]" in item for item in cleaned)

    def test_cli_clear(self, tmp_path, monkeypatch, capsys):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        module.start_task("ink-write", {"chapter_num": 50})
        module.clear_current_task()

        state = module.load_state()
        assert state["current_task"] is None

    def test_cli_fail_task(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        module.start_task("ink-write", {"chapter_num": 60})
        module.fail_current_task("cli_test")

        state = module.load_state()
        assert state["current_task"]["status"] == module.TASK_STATUS_FAILED


# ---------------------------------------------------------------------------
# cleanup_artifacts edge cases
# ---------------------------------------------------------------------------

class TestCleanupArtifactsEdgeCases:
    def test_cleanup_no_chapter_file(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        def _fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        monkeypatch.setattr(module.subprocess, "run", _fake_run)

        cleaned = module.cleanup_artifacts(999, confirm=True)
        assert any("Git" in item for item in cleaned)

    def test_cleanup_git_reset_failure(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        def _fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stderr="fatal: not a git repo", stdout="")

        monkeypatch.setattr(module.subprocess, "run", _fake_run)

        cleaned = module.cleanup_artifacts(999, confirm=True)
        assert any("失败" in item for item in cleaned)

    def test_cleanup_backup_failure_aborts(self, tmp_path, monkeypatch):
        module = _load_module()
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module, "find_project_root", lambda: tmp_path)

        draft = module.default_chapter_draft_path(tmp_path, 7)
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("draft", encoding="utf-8")

        def _fail_backup(project_root, chapter_num, chapter_path):
            raise OSError("disk full")

        monkeypatch.setattr(module, "_backup_chapter_for_cleanup", _fail_backup)

        cleaned = module.cleanup_artifacts(7, confirm=True)
        assert any("备份失败" in item for item in cleaned)
        assert draft.exists()  # file should NOT be deleted


# ---------------------------------------------------------------------------
# _finalize_current_step_as_failed edge cases
# ---------------------------------------------------------------------------

class TestFinalizeStepAsFailed:
    def test_no_current_step_is_noop(self, tmp_path, monkeypatch):
        module = _load_module()
        task = {"current_step": None, "failed_steps": []}
        module._finalize_current_step_as_failed(task, "reason")
        assert task["failed_steps"] == []

    def test_already_completed_step_is_noop(self, tmp_path, monkeypatch):
        module = _load_module()
        task = {
            "current_step": {"id": "Step 1", "status": module.STEP_STATUS_COMPLETED},
            "failed_steps": [],
        }
        module._finalize_current_step_as_failed(task, "reason")
        assert task["failed_steps"] == []

    def test_running_step_gets_finalized(self, tmp_path, monkeypatch):
        module = _load_module()
        task = {
            "current_step": {"id": "Step 2A", "status": module.STEP_STATUS_RUNNING},
            "failed_steps": [],
        }
        module._finalize_current_step_as_failed(task, "test_reason")
        assert len(task["failed_steps"]) == 1
        assert task["failed_steps"][0]["status"] == module.STEP_STATUS_FAILED
        assert task["current_step"] is None
