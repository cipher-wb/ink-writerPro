"""Shared test fixtures for data_modules test suite.

Extracted fixtures:
- temp_project: 创建临时项目目录（含 .ink 子目录及标准子文件夹）
"""

import warnings

import pytest

from data_modules.config import DataModulesConfig


# ---------------------------------------------------------------------------
# Warning filters
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Suppress known noisy warnings that leak from third-party / stdlib code."""
    config.addinivalue_line(
        "filterwarnings",
        "ignore:unclosed database:ResourceWarning",
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录（含 .ink 子目录及标准子文件夹）"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg
