"""Dashboard server.py 单元测试 — 验证项目路径解析逻辑。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_dashboard_parent = str(Path(__file__).resolve().parents[3])
if _dashboard_parent not in sys.path:
    sys.path.insert(0, _dashboard_parent)

pytest.importorskip("fastapi")

from dashboard.server import _resolve_project_root


# ---------------------------------------------------------------------------
# _resolve_project_root
# ---------------------------------------------------------------------------

class TestResolveProjectRoot:
    """按优先级解析 PROJECT_ROOT 的测试。"""

    def test_cli_root_takes_highest_priority(self, tmp_path):
        """CLI 参数优先于一切。"""
        result = _resolve_project_root(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_env_var_when_no_cli(self, tmp_path, monkeypatch):
        """无 CLI 参数时使用 INK_PROJECT_ROOT 环境变量。"""
        monkeypatch.setenv("INK_PROJECT_ROOT", str(tmp_path))
        result = _resolve_project_root(None)
        assert result == tmp_path.resolve()

    def test_claude_pointer_file(self, tmp_path, monkeypatch):
        """无 CLI 和环境变量时，从 .claude 指针读取。"""
        monkeypatch.delenv("INK_PROJECT_ROOT", raising=False)
        project = tmp_path / "novel"
        ink_dir = project / ".ink"
        ink_dir.mkdir(parents=True)
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".ink-current-project").write_text(
            str(project), encoding="utf-8"
        )

        monkeypatch.chdir(tmp_path)
        result = _resolve_project_root(None)
        assert result == project.resolve()

    def test_cwd_fallback(self, tmp_path, monkeypatch):
        """CWD 包含 .ink/state.json 时兜底。"""
        monkeypatch.delenv("INK_PROJECT_ROOT", raising=False)
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = _resolve_project_root(None)
        assert result == tmp_path.resolve()

    def test_no_project_found_exits(self, tmp_path, monkeypatch):
        """无法定位项目时 sys.exit(1)。"""
        monkeypatch.delenv("INK_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            _resolve_project_root(None)
        assert exc_info.value.code == 1

    def test_invalid_pointer_falls_through(self, tmp_path, monkeypatch):
        """指针文件指向不存在的目录时跳过。"""
        monkeypatch.delenv("INK_PROJECT_ROOT", raising=False)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".ink-current-project").write_text(
            "/nonexistent/path", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            _resolve_project_root(None)

    def test_empty_pointer_file_falls_through(self, tmp_path, monkeypatch):
        """空指针文件被忽略。"""
        monkeypatch.delenv("INK_PROJECT_ROOT", raising=False)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".ink-current-project").write_text("", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            _resolve_project_root(None)


# ---------------------------------------------------------------------------
# main() 函数分支
# ---------------------------------------------------------------------------

class TestMain:
    """main() 的参数解析和启动逻辑。"""

    def test_main_invokes_uvicorn(self, tmp_path, monkeypatch):
        """验证 main() 能正确调用 uvicorn.run。"""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")

        monkeypatch.setattr(
            "sys.argv",
            ["server", "--project-root", str(tmp_path), "--no-browser"],
        )
        mock_uvicorn = MagicMock()
        monkeypatch.setattr("uvicorn.run", mock_uvicorn)

        from dashboard.server import main
        main()

        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs[1]["host"] == "127.0.0.1"
        assert call_kwargs[1]["port"] == 8765

    def test_main_custom_port(self, tmp_path, monkeypatch):
        """验证自定义端口参数。"""
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text("{}", encoding="utf-8")

        monkeypatch.setattr(
            "sys.argv",
            ["server", "--project-root", str(tmp_path), "--port", "9999", "--no-browser"],
        )
        mock_uvicorn = MagicMock()
        monkeypatch.setattr("uvicorn.run", mock_uvicorn)

        from dashboard.server import main
        main()

        assert mock_uvicorn.call_args[1]["port"] == 9999
