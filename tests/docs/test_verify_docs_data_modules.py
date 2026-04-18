"""v16 US-006：verify_docs.py 的 data_modules 导入检测单元测试。

覆盖：
- 检测 ``from data_modules.x import y`` 命中。
- 检测 ``import data_modules`` 命中。
- 白名单目录（archive/ / benchmark/ / tests/migration/ / ralph/）不触发。
- 无违规代码返回空 findings。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verify_docs import check_no_data_modules_imports


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def scan_root(tmp_path: Path) -> Path:
    (tmp_path / "ink_writer").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "benchmark").mkdir()
    return tmp_path


class TestNoDataModulesImports:
    def test_from_import_flagged(self, scan_root: Path) -> None:
        _write(scan_root / "ink_writer" / "bad.py", "from data_modules.foo import bar\n")
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "ink_writer",), root=scan_root
        )
        assert findings, "期望检测到 data_modules 导入"
        assert not findings[0].ok

    def test_bare_import_flagged(self, scan_root: Path) -> None:
        _write(scan_root / "ink_writer" / "bad.py", "import data_modules as dm\n")
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "ink_writer",), root=scan_root
        )
        assert findings
        assert not findings[0].ok

    def test_archive_whitelisted(self, scan_root: Path) -> None:
        _write(scan_root / "archive" / "legacy.py", "from data_modules.x import y\n")
        # archive 走白名单 → 不报
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "archive",), root=scan_root
        )
        assert findings == []

    def test_benchmark_whitelisted(self, scan_root: Path) -> None:
        _write(scan_root / "benchmark" / "perf.py", "import data_modules\n")
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "benchmark",), root=scan_root
        )
        assert findings == []

    def test_clean_code_no_findings(self, scan_root: Path) -> None:
        _write(scan_root / "ink_writer" / "ok.py", "from ink_writer.core.cli import ink\n")
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "ink_writer",), root=scan_root
        )
        assert findings == []

    def test_missing_dir_is_noop(self, scan_root: Path) -> None:
        findings = check_no_data_modules_imports(
            scan_dirs=(scan_root / "does-not-exist",), root=scan_root
        )
        assert findings == []
