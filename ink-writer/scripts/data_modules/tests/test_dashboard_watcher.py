"""Dashboard watcher.py 单元测试 — 验证文件监听和 SSE 推送逻辑。"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_dashboard_parent = str(Path(__file__).resolve().parents[3])
if _dashboard_parent not in sys.path:
    sys.path.insert(0, _dashboard_parent)

pytest.importorskip("watchdog")

from dashboard.watcher import FileWatcher, _InkFileHandler


# ---------------------------------------------------------------------------
# _InkFileHandler
# ---------------------------------------------------------------------------

class TestInkFileHandler:
    """测试文件事件过滤器。"""

    def test_ignores_directory_events(self):
        cb = MagicMock()
        handler = _InkFileHandler(cb)
        event = MagicMock(is_directory=True, src_path="/a/.ink/state.json")
        handler.on_modified(event)
        handler.on_created(event)
        cb.assert_not_called()

    def test_notifies_on_state_json_modified(self):
        cb = MagicMock()
        handler = _InkFileHandler(cb)
        event = MagicMock(is_directory=False, src_path="/project/.ink/state.json")
        handler.on_modified(event)
        cb.assert_called_once_with("/project/.ink/state.json", "modified")

    def test_notifies_on_index_db_created(self):
        cb = MagicMock()
        handler = _InkFileHandler(cb)
        event = MagicMock(is_directory=False, src_path="/project/.ink/index.db")
        handler.on_created(event)
        cb.assert_called_once_with("/project/.ink/index.db", "created")

    def test_notifies_on_workflow_state(self):
        cb = MagicMock()
        handler = _InkFileHandler(cb)
        event = MagicMock(is_directory=False, src_path="/p/.ink/workflow_state.json")
        handler.on_modified(event)
        cb.assert_called_once()

    def test_ignores_unrelated_files(self):
        cb = MagicMock()
        handler = _InkFileHandler(cb)
        event = MagicMock(is_directory=False, src_path="/project/.ink/backup.bak")
        handler.on_modified(event)
        handler.on_created(event)
        cb.assert_not_called()

    def test_watch_names_is_complete(self):
        assert _InkFileHandler.WATCH_NAMES == {"state.json", "index.db", "workflow_state.json"}


# ---------------------------------------------------------------------------
# FileWatcher - subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestFileWatcherSubscription:

    def test_subscribe_returns_queue(self):
        watcher = FileWatcher()
        q = watcher.subscribe()
        assert isinstance(q, asyncio.Queue)
        assert q in watcher._subscribers

    def test_unsubscribe_removes_queue(self):
        watcher = FileWatcher()
        q = watcher.subscribe()
        watcher.unsubscribe(q)
        assert q not in watcher._subscribers

    def test_unsubscribe_nonexistent_is_safe(self):
        watcher = FileWatcher()
        q = asyncio.Queue()
        watcher.unsubscribe(q)  # should not raise


# ---------------------------------------------------------------------------
# FileWatcher - _dispatch
# ---------------------------------------------------------------------------

class TestFileWatcherDispatch:

    def test_dispatch_sends_to_all_subscribers(self):
        watcher = FileWatcher()
        q1 = watcher.subscribe()
        q2 = watcher.subscribe()
        watcher._dispatch('{"file":"state.json"}')
        assert not q1.empty()
        assert not q2.empty()

    def test_dispatch_removes_full_queues(self):
        watcher = FileWatcher()
        q = asyncio.Queue(maxsize=1)
        watcher._subscribers.append(q)
        q.put_nowait("fill")
        watcher._dispatch("overflow")
        assert q not in watcher._subscribers

    def test_dispatch_empty_subscribers(self):
        watcher = FileWatcher()
        watcher._dispatch("msg")  # should not raise


# ---------------------------------------------------------------------------
# FileWatcher - _on_change
# ---------------------------------------------------------------------------

class TestFileWatcherOnChange:

    def test_on_change_ignores_closed_loop(self):
        watcher = FileWatcher()
        loop = MagicMock()
        loop.is_closed.return_value = True
        watcher._loop = loop
        watcher._on_change("/p/state.json", "modified")
        loop.call_soon_threadsafe.assert_not_called()

    def test_on_change_dispatches_to_loop(self):
        watcher = FileWatcher()
        loop = MagicMock()
        loop.is_closed.return_value = False
        watcher._loop = loop
        watcher._on_change("/p/.ink/state.json", "modified")
        loop.call_soon_threadsafe.assert_called_once()
        args = loop.call_soon_threadsafe.call_args
        assert args[0][0] == watcher._dispatch
        msg = json.loads(args[0][1])
        assert msg["file"] == "state.json"
        assert msg["kind"] == "modified"
        assert "ts" in msg

    def test_on_change_without_loop(self):
        watcher = FileWatcher()
        watcher._on_change("/p/state.json", "modified")  # should not raise


# ---------------------------------------------------------------------------
# FileWatcher - start / stop
# ---------------------------------------------------------------------------

class TestFileWatcherLifecycle:

    def test_start_creates_observer(self, tmp_path):
        watcher = FileWatcher()
        loop = MagicMock()
        loop.is_closed.return_value = False
        watch_dir = tmp_path / ".ink"
        watch_dir.mkdir()

        watcher.start(watch_dir, loop)
        assert watcher._observer is not None
        assert watcher._loop is loop

        watcher.stop()
        assert watcher._observer is None

    def test_stop_without_start(self):
        watcher = FileWatcher()
        watcher.stop()  # should not raise

    def test_double_stop(self, tmp_path):
        watcher = FileWatcher()
        loop = MagicMock()
        watch_dir = tmp_path / ".ink"
        watch_dir.mkdir()
        watcher.start(watch_dir, loop)
        watcher.stop()
        watcher.stop()  # second stop should be safe
