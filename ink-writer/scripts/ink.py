#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ink 统一入口脚本（无须 `cd`）

用法示例：
  python "<SCRIPTS_DIR>/ink.py" preflight
  python "<SCRIPTS_DIR>/ink.py" where
  python "<SCRIPTS_DIR>/ink.py" index stats

v16 US-006（FIX-11 收尾）：把旧版 sys.path.insert 裸路径 hack 替换为显式
repo_root 判断——若 ``ink_writer`` 不可直接 import（未安装 / PYTHONPATH 未设），
仅在此入口脚本回退添加仓库根，不再污染全链路 sys.path。
"""

from __future__ import annotations

import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio


def main() -> None:
    # 确保 ``ink_writer`` 可 import：优先走已安装包或已设 PYTHONPATH；
    # 仅在两者都缺失时回退向仓库根注入（单一兜底，不再 insert scripts_dir）。
    try:
        import ink_writer  # noqa: F401 - import for side-effect only
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

    from ink_writer.core.cli.ink import main as _main

    _main()


if __name__ == "__main__":
    enable_windows_utf8_stdio(skip_in_pytest=True)
    main()
