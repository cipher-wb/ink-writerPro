"""Unit tests for ink-writer/scripts/runtime_compat.py Windows helpers.

All helpers are no-ops on macOS/Linux, so tests simulate Windows via
monkeypatching ``sys.platform`` where appropriate.
"""
from __future__ import annotations

import asyncio

import pytest

import runtime_compat as rc


def _reset_caches() -> None:
    rc._PROACTOR_POLICY_SET = False
    rc._SYMLINK_PRIVILEGE_CACHE = None
    rc._PYTHON_LAUNCHER_CACHE = None


@pytest.fixture(autouse=True)
def _reset() -> None:
    _reset_caches()
    yield
    _reset_caches()


class TestSetWindowsProactorPolicy:
    def test_non_windows_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.sys, "platform", "darwin")
        assert rc.set_windows_proactor_policy() is False

    def test_non_windows_noop_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.sys, "platform", "linux")
        assert rc.set_windows_proactor_policy() is False


class TestHasSymlinkPrivilege:
    def test_non_windows_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.sys, "platform", "darwin")
        assert rc._has_symlink_privilege() is True


class TestFindPythonLauncher:
    def test_non_windows_returns_python3(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rc.sys, "platform", "darwin")
        assert rc.find_python_launcher() == "python3"

    def test_result_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rc.sys, "platform", "linux")
        first = rc.find_python_launcher()
        monkeypatch.setattr(rc.sys, "platform", "darwin")
        second = rc.find_python_launcher()
        assert first == second == "python3"


@pytest.mark.windows
class TestWindowsBranches:  # pragma: no cover
    def test_proactor_policy_applies(self) -> None:
        assert rc.set_windows_proactor_policy() is True
        policy = asyncio.get_event_loop_policy()
        assert isinstance(policy, asyncio.WindowsProactorEventLoopPolicy)

    def test_proactor_policy_idempotent(self) -> None:
        rc.set_windows_proactor_policy()
        assert rc.set_windows_proactor_policy() is True

    def test_find_launcher_returns_known_value(self) -> None:
        launcher = rc.find_python_launcher()
        assert launcher in {"py -3", "python3", "python"}

    def test_has_symlink_privilege_returns_bool(self) -> None:
        assert isinstance(rc._has_symlink_privilege(), bool)
